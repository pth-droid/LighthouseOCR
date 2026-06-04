import os
import json
import copy
import logging
import random
import time
import ast
import re
try:
    import google.genai as genai
    from google.genai import types
    from google.genai.errors import APIError
except ImportError:
    genai = None
    types = None
    APIError = None

from core_rate_limiter import global_rate_limiter, EngineCancellationError
from core_llm_client import parse_json_response, generate_with_fallback
from path_utils import get_asset_path

_CALC_SKILL_FILE = get_asset_path("ocr_calculation_skill.md")
from data_manager import DataManager


def _should_skip_llm(raw_json_obj: dict) -> bool:
    # Supplier reverse lookup now belongs to KIE/enrichment, not the calculator.
    return True



def _to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = value.replace(",", "")
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_percent(text) -> float | None:
    if not text:
        return None
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', str(text))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _parse_money_values(text) -> list[float]:
    if not text:
        return []
    candidates = re.findall(r'\d[\d.,]{2,}', str(text))
    values = []
    for token in candidates:
        cleaned = token.replace(".", "").replace(",", "")
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


# _append_note removed (L-1): dead code — never called, note-building uses f-strings directly.


def _fmt_money(value: float) -> str:
    return f"{int(round(value, 0)):,}".replace(",", " ")


def _normalize_payment_method(text) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    return re.sub(r"\s+", " ", value)


def _build_standardized_note(
    base_unit_price: float,
    per_unit_vat: float,
    per_unit_discount: float,
    per_unit_shipping: float,
    adjusted_unit_price: float,
    payment_method: str,
) -> str:
    # Nếu giá không đổi so với bill gốc (và không có phí/thuế/chiết khấu lẻ)
    # thì không cần in công thức tính toán.
    has_math = (per_unit_vat > 0 or per_unit_shipping > 0 or per_unit_discount > 0)
    # So sánh với sai số 1 VND
    price_changed = abs(base_unit_price - adjusted_unit_price) > 1.0
    
    calc_text = ""
    if has_math or price_changed:
        parts = [f"Gia unit: {_fmt_money(base_unit_price)}"]
        if per_unit_vat > 0:
            parts.append(f"+ VAT {_fmt_money(per_unit_vat)}")
        if per_unit_shipping > 0:
            parts.append(f"+ Phi {_fmt_money(per_unit_shipping)}")
        if per_unit_discount > 0:
            parts.append(f"- CK {_fmt_money(per_unit_discount)}")
        calc_text = " ".join(parts) + f" = {_fmt_money(adjusted_unit_price)}"
    
    payment_method = _normalize_payment_method(payment_method)
    if payment_method:
        if calc_text:
            return f"{calc_text} | TT: {payment_method}"
        return f"TT: {payment_method}"
    return calc_text


def _detect_vat_inclusive_totals(raw_items: list, line_bases: list) -> bool:
    # C-1: Skip items whose qty came from FIX-2 fallback — they have no raw VAT to compare
    """
    Phát hiện hoá đơn mà cột 'Thành tiền' (total_price) ĐÃ bao gồm VAT trên từng dòng.
    
    Ví dụ điển hình: Moonmilk Market — mỗi dòng ghi rõ Đơn giá (pre-VAT), Tiền VAT,
    và Thành tiền (= Đơn giá × SL + Tiền VAT). Nếu Calculator cộng VAT lần nữa
    sẽ bị double-count.

    Chiến lược: So sánh total_price với (unit_price × qty + raw_vat_amount).
    Nếu đa số items khớp pattern VAT-inclusive → trả True.
    """
    vote_inclusive = 0
    vote_exclusive = 0

    for idx, raw_item in enumerate(raw_items):
        if idx >= len(line_bases):
            break
        base = line_bases[idx]
        # C-1: Bỏ qua item dùng fallback qty=1 (FIX-2) — không có raw VAT để đánh giá
        if base.get("_is_qty_fallback"):
            continue
        qty = base["qty"]
        base_unit_price = base["base_unit_price"]
        base_total_price = base["base_total_price"]
        raw_vat_amount = _to_float(raw_item.get("raw_vat_amount"), 0.0)

        # Cần đủ 4 giá trị để đánh giá
        if qty <= 0 or base_unit_price <= 0 or base_total_price <= 0 or raw_vat_amount <= 0:
            continue

        pre_vat_total = qty * base_unit_price
        post_vat_total = pre_vat_total + raw_vat_amount

        # Tolerance 2% cho sai số làm tròn
        tolerance = base_total_price * 0.02
        diff_to_post_vat = abs(base_total_price - post_vat_total)
        diff_to_pre_vat = abs(base_total_price - pre_vat_total)

        if diff_to_post_vat <= tolerance and diff_to_post_vat < diff_to_pre_vat:
            vote_inclusive += 1
        elif diff_to_pre_vat <= tolerance:
            vote_exclusive += 1

    # Chỉ cần có bằng chứng inclusive VÀ không bị exclusive áp đảo
    return vote_inclusive > 0 and vote_inclusive >= vote_exclusive


def _normalize_pricing_basis(raw_json_obj: dict, calc_result: dict) -> dict:
    raw_items = raw_json_obj.get("items", []) or []
    result_items = calc_result.get("items", []) or []
    tx_info_raw = raw_json_obj.get("transaction_info", {}) or {}
    totals_raw = raw_json_obj.get("totals", {}) or {}

    tx_out = dict(calc_result.get("transaction_info", {}) or {})
    if not tx_out.get("department"):
        tx_out["department"] = raw_json_obj.get("transaction_info", {}).get("department")
    calc_result["transaction_info"] = tx_out

    discount_rate = _parse_percent(tx_info_raw.get("raw_discount_info"))
    discount_money_values = _parse_money_values(tx_info_raw.get("raw_discount_info"))
    shipping_money_values = _parse_money_values(tx_info_raw.get("raw_shipping_fee_info"))
    # Dùng min() thay vì max() để tránh bắt nhầm ngưỡng áp dụng (vd: "CK 100k cho đơn từ 500k" → min=100, max=500)
    order_discount_amount = min(discount_money_values) if discount_money_values else 0.0
    # H-1: Khi đã có discount_rate (%), KHÔNG áp thêm order_discount_amount tránh tính đôi
    if discount_rate is not None:
        order_discount_amount = 0.0
    shipping_amount = min(shipping_money_values) if shipping_money_values else 0.0
    payment_method = tx_info_raw.get("raw_payment_method")

    line_bases = []
    for idx, raw_item in enumerate(raw_items):
        qty = _to_float(raw_item.get("quantity"), 0.0)
        base_unit_price = _to_float(raw_item.get("unit_price"), 0.0)
        base_total_price = _to_float(raw_item.get("total_price"), 0.0)
        if qty > 0 and base_total_price <= 0 and base_unit_price > 0:
            base_total_price = round(qty * base_unit_price, 0)
        if qty > 0 and base_unit_price <= 0 and base_total_price > 0:
            base_unit_price = round(base_total_price / qty, 0)
        # FIX-2 (Case 5): Chỉ có total_price, không có qty và unit_price
        # Fallback: qty = 1, unit_price = total_price (khớp với rule LLM calc skill)
        _is_qty_fallback = False
        if qty <= 0 and base_unit_price <= 0:
            if base_total_price > 0:
                qty = 1.0
                base_unit_price = base_total_price
                _is_qty_fallback = True  # C-1: đánh dấu để VAT voting bỏ qua
                logging.warning(
                    f"[Calculator] FIX-2 (Case 5): Item '{raw_item.get('product_name', '?')}' "
                    f"thiếu qty/unit_price — áp dụng fallback qty=1, unit_price=total_price={base_total_price}"
                )
            else:
                # Cả 3 đều 0 hoặc None -> Giữ nguyên để tránh chia cho 0 sau này, nhưng gán qty=1 làm mẫu
                qty = 1.0
                base_unit_price = 0.0
                base_total_price = 0.0
                _is_qty_fallback = True
        # RISK-C3 fix: Phát hiện đơn giá viết tắt x1000.
        # Phiếu viết tay thường bỏ 3 số 0 cuối. Có 2 trường hợp:
        #   Case 1: Chỉ unit_price viết tắt, total_price là số thực
        #           VD: unit=85, qty=10, total=850,000 → ratio ≈ 1000
        #   Case 2: CẢ unit_price VÀ total_price đều viết tắt (phổ biến nhất!)
        #           VD: unit=85, qty=10, total=850 → ratio ≈ 1
        #           VD: unit=1325, qty=2, total=2650 → ratio ≈ 1
        #           Phát hiện: ratio ≈ 1 NHƯNG total < 10,000 VND (ngưỡng F&B wholesale)
        if base_unit_price > 0 and qty > 0 and base_total_price > 0:
            implied_total_at_written_price = qty * base_unit_price
            ratio = base_total_price / implied_total_at_written_price
            if 950 <= ratio <= 1050:
                # Case 1: Chỉ unit_price bị viết tắt
                logging.warning(
                    f"[Calculator] x1000 Case 1 (unit only): unit_price {base_unit_price} "
                    f"→ {int(base_unit_price * 1000)} "
                    f"(total={base_total_price}, qty={qty}, ratio={ratio:.1f}x)"
                )
                base_unit_price *= 1000
                # base_total_price giữ nguyên — đây là anchor
            elif 0.95 <= ratio <= 1.05 and base_total_price < 10_000:
                # Case 2: Cả hai đều viết tắt — giá trị quá thấp cho F&B wholesale
                logging.warning(
                    f"[Calculator] x1000 Case 2 (both shorthand): "
                    f"unit {base_unit_price}→{int(base_unit_price * 1000)}, "
                    f"total {base_total_price}→{int(base_total_price * 1000)} "
                    f"(qty={qty})"
                )
                base_unit_price *= 1000
                base_total_price *= 1000
        line_bases.append({
            "idx": idx,
            "qty": qty,
            "base_unit_price": base_unit_price,
            "base_total_price": base_total_price,
            "_is_qty_fallback": _is_qty_fallback,  # C-1
        })

    # ── VAT-Inclusive Detection & Deduplication ──────────────────────────
    # Một số hoá đơn (ví dụ: Moonmilk Market) ghi Thành tiền ĐÃ gộp VAT
    # trên từng dòng, rồi cuối bill lại tổng kết VAT thêm lần nữa.
    # Nếu không trừ VAT khỏi base trước khi tính → double-count.
    vat_inclusive = _detect_vat_inclusive_totals(raw_items, line_bases)
    if vat_inclusive:
        logging.warning(
            "[Calculator] ⚠️ VAT-INCLUSIVE DETECTED: Thành tiền trên từng dòng đã "
            "bao gồm VAT. Tự động trừ VAT khỏi base_total_price để tránh tính đúp."
        )
        for idx, raw_item in enumerate(raw_items):
            raw_vat_amount = _to_float(raw_item.get("raw_vat_amount"), 0.0)
            if raw_vat_amount > 0 and line_bases[idx]["base_total_price"] > raw_vat_amount:
                line_bases[idx]["base_total_price"] -= raw_vat_amount
                # Không cập nhật base_unit_price vì cột Đơn giá trên bill
                # thường đã là giá pre-VAT (ví dụ: 16,166.67 cho Moonmilk)
    # ────────────────────────────────────────────────────────────────────

    base_subtotal = sum(x["base_total_price"] for x in line_bases)
    if base_subtotal <= 0:
        return calc_result

    normalized_items = []
    vat_total = 0.0
    discount_total = 0.0
    shipping_total = 0.0
    net_total_before_vat = 0.0
    grand_total = 0.0

    for idx, raw_item in enumerate(raw_items):
        result_item = result_items[idx] if idx < len(result_items) else {}
        base = line_bases[idx]
        qty = base["qty"]
        base_unit_price = base["base_unit_price"]
        base_total_price = base["base_total_price"]
        ratio = (base_total_price / base_subtotal) if base_subtotal > 0 else 0.0

        line_discount_amount = 0.0
        if discount_rate is not None:
            line_discount_amount = round(base_total_price * discount_rate / 100.0, 0)
        elif order_discount_amount > 0:
            line_discount_amount = round(order_discount_amount * ratio, 0)

        discounted_total = max(base_total_price - line_discount_amount, 0.0)
        line_shipping_amount = round(shipping_amount * ratio, 0) if shipping_amount > 0 else 0.0

        raw_vat_amount = _to_float(raw_item.get("raw_vat_amount"), 0.0)
        raw_vat_rate = _parse_percent(raw_item.get("raw_vat_rate"))
        fallback_vat_rate = _to_float(totals_raw.get("vat_percentage"), 0.0) or None
        vat_rate = raw_vat_rate if raw_vat_rate is not None else fallback_vat_rate

        if raw_vat_amount > 0:
            line_vat_amount = raw_vat_amount
        elif vat_rate:
            line_vat_amount = round(discounted_total * vat_rate / 100.0, 0)
        else:
            line_vat_amount = 0.0

        payable_total = discounted_total + line_vat_amount + line_shipping_amount
        per_unit_discount = (line_discount_amount / qty) if qty > 0 else 0.0
        per_unit_vat = (line_vat_amount / qty) if qty > 0 else 0.0
        per_unit_shipping = (line_shipping_amount / qty) if qty > 0 else 0.0
        adjusted_unit_price = (payable_total / qty) if qty > 0 else 0.0

        formula_text = _build_standardized_note(
            base_unit_price=base_unit_price,
            per_unit_vat=per_unit_vat,
            per_unit_discount=per_unit_discount,
            per_unit_shipping=per_unit_shipping,
            adjusted_unit_price=adjusted_unit_price,
            payment_method=payment_method,
        )
        notes = formula_text

        merged_item = dict(result_item)
        merged_item.update({
            "product_name": result_item.get("product_name") or raw_item.get("product_name"),
            "unit": result_item.get("unit") or raw_item.get("unit"),
            # H-4: Ưu tiên qty đã normalize từ line_bases (FIX-2 fallback hoặc tính lại)
            "quantity": qty if qty > 0 else raw_item.get("quantity", result_item.get("quantity")),
            "unit_price": int(round(adjusted_unit_price, 0)) if adjusted_unit_price else 0,
            "total_price": int(round(payable_total, 0)) if payable_total else 0,
            "base_unit_price": int(round(base_unit_price, 0)) if base_unit_price else 0,
            "base_total_price": int(round(base_total_price, 0)) if base_total_price else 0,
            "pricing_basis": "ADJUSTED_UNIT_PRICE_WITH_TRACE",
            "discount_amount": int(round(line_discount_amount, 0)),
            "net_total_before_vat": int(round(discounted_total, 0)),
            "vat_rate": vat_rate,
            "vat_amount": int(round(line_vat_amount, 0)),
            "shipping_allocated": int(round(line_shipping_amount, 0)),
            "payable_total": int(round(payable_total, 0)),
            "base_pricing_note": formula_text,
            "notes": notes,
        })
        normalized_items.append(merged_item)

        vat_total += line_vat_amount
        discount_total += line_discount_amount
        shipping_total += line_shipping_amount
        net_total_before_vat += discounted_total
        grand_total += payable_total

    calc_result["items"] = normalized_items

    totals_out = dict(calc_result.get("totals", {}) or {})
    totals_out.update({
        "pricing_basis": "unit_price = adjusted payable unit price; base_unit_price/base_total_price preserve original invoice values",
        "sub_total": int(round(base_subtotal, 0)),
        "discount_amount": int(round(discount_total, 0)),
        "net_total_before_vat": int(round(net_total_before_vat, 0)),
        "vat_amount": int(round(vat_total, 0)),
        "shipping_amount": int(round(shipping_total, 0)),
        "total_amount": int(round(grand_total, 0)),
    })
    if totals_out.get("vat_percentage") in (None, "", 0):
        totals_out["vat_percentage"] = totals_raw.get("vat_percentage", 0)

    # FIX-4 (Case 7B): Phát hiện tổng phiếu tay lệch tổng tính được
    raw_total_amount = _to_float(totals_raw.get("total_amount"), 0.0)
    if raw_total_amount > 0 and grand_total > 0:
        divergence = abs(grand_total - raw_total_amount) / raw_total_amount
        if divergence > 0.05:  # Lệch > 5%
            totals_out["total_discrepancy_warning"] = (
                f"[CẢNH BÁO: Tổng phiếu tay ({int(raw_total_amount):,}) lệch {divergence:.1%} "
                f"so với tổng tính được ({int(grand_total):,}). Kiểm tra lại phiếu gốc.]"
            )
            logging.warning(
                f"[Calculator] FIX-4: Total divergence {divergence:.1%} — "
                f"invoice total={int(raw_total_amount)}, computed={int(grand_total)}"
            )

    calc_result["totals"] = totals_out

    tx_out = dict(calc_result.get("transaction_info", {}) or {})
    tx_out["pricing_policy"] = (
        "unit_price is stored as adjusted payable unit price. base_unit_price/base_total_price preserve original invoice values. "
        "If order-level discount or fees exist, they are allocated proportionally by line value, not evenly by line count. "
        "VAT is calculated on the value after discount."
    )
    calc_result["transaction_info"] = tx_out

    return calc_result

class LLMCalculator:
    def __init__(self, api_key: str, data_store: DataManager):
        if genai is None:
            raise RuntimeError(
                "google-genai SDK is not installed. Install dependency 'google-genai' to use LLM calculator."
            )
        self.api_key = api_key
        self.data_store = data_store
        self.client = genai.Client(api_key=self.api_key)
        self.prompt_template = ""
        
        try:
            with open(_CALC_SKILL_FILE, "r", encoding="utf-8") as f:
                self.prompt_template = f.read()
            
        except Exception as e:
            raise RuntimeError(f"Engine failed to build Calculation Prompts: {e}")

    def run_calculation(self, raw_json_obj: dict, stop_event=None, status_callback=None) -> dict:
        # --- Fast-path: bỏ qua LLM nếu không cần Reverse Lookup NCC ---
        if _should_skip_llm(raw_json_obj):
            if status_callback:
                status_callback("⚡ NCC đã xác định — bỏ qua LLM Toán, tính trực tiếp bằng Python.")
            result = copy.deepcopy(raw_json_obj)
            # Gắn telemetry giả để downstream không bị lỗi thiếu field
            if "_telemetry" in raw_json_obj:
                result["_telemetry"] = copy.deepcopy(raw_json_obj["_telemetry"])
                result["_telemetry"].update({"calc_prompt_tokens": 0, "calc_response_tokens": 0})
            return _normalize_pricing_basis(raw_json_obj, result)

        # --- Slow-path: cần LLM để Reverse Lookup NCC hoặc diễn giải phức tạp ---
        if status_callback:
            status_callback("🧮 NCC chưa rõ — kích hoạt LLM Toán để Reverse Lookup và chuẩn hoá...")

        raw_json_str = json.dumps(raw_json_obj, ensure_ascii=False)
        context_block = f"SUPPLIER_MASTER_LIST_CONTEXT:\n{self.data_store.suppliers_context_str}"
        combined_prompt = f"{self.prompt_template}\n\n{context_block}\n\nRAW_JSON_INPUT:\n{raw_json_str}"

        try:
            models_to_try = [
                {"name": self.data_store.models.get("light_primary"), "label": "Gemini 3.1 Flash-Lite", "is_primary": True},
                {"name": self.data_store.models.get("light_fallback"), "label": "Gemini 2.5 Flash Fallback", "is_primary": False}
            ]
            raw_text, _, usage_meta = generate_with_fallback(
                self.client, models_to_try,
                contents_fn=lambda _: [combined_prompt],
                data_store=self.data_store,
                rate_bucket_fn=lambda _: "flash",
                base_wait_fn=lambda _: 10,
                stop_event=stop_event,
                status_callback=status_callback,
            )
            usage = {
                "calc_prompt_tokens": getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0,
                "calc_response_tokens": getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0,
            }
            result = parse_json_response(raw_text)

            if "_telemetry" in raw_json_obj:
                result["_telemetry"] = raw_json_obj["_telemetry"]
                result["_telemetry"].update(usage)
            else:
                result["_telemetry"] = usage

            if "document_info" in raw_json_obj:
                result["document_info"] = raw_json_obj["document_info"]

            return _normalize_pricing_basis(raw_json_obj, result)

        except EngineCancellationError:
            raise
        except Exception as e:
            if APIError is not None and isinstance(e, APIError):
                if status_callback:
                    status_callback("[WARN] LLM API error, fallback to raw normalized data.")
                logging.exception("[Calculator] LLM API failure")
                return _normalize_pricing_basis(raw_json_obj, copy.deepcopy(raw_json_obj))
            logging.exception("[Calculator] Unexpected calculation failure")
            raise

_calc_instance = None
_calc_data_version = None
def get_calculator(api_key: str, data_store: DataManager):
    global _calc_instance, _calc_data_version
    if not _calc_instance or _calc_instance.api_key != api_key or _calc_data_version != data_store._data_version:
        _calc_instance = LLMCalculator(api_key, data_store)
        _calc_data_version = data_store._data_version
    return _calc_instance
