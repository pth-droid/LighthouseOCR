import re
import unicodedata
import json
import logging
from typing import List, Dict, Any, Tuple

import google.genai as genai
from google.genai import types
from rapidfuzz import fuzz, process as rfprocess

from unit_converter import _match_unit, _VOLUME_UNITS, _WEIGHT_UNITS
from core_rate_limiter import global_rate_limiter


def _get_item_department(raw_group: str) -> str:
    group = str(raw_group or "").strip().upper()
    for dept_key in ("RANG", "BANH", "BAR", "BEP"):
        if group.startswith(dept_key):
            return dept_key
    return ""


def _clean_ocr_name(raw: str) -> str:
    """
    Tiền xử lý tên mặt hàng từ OCR trước khi so khớp.
    1. Loại bỏ phần tiếng Anh trong ngoặc đơn (case-insensitive)
    2. Loại bỏ đuôi text full-English (khi OCR scan cả tên EN không có ngoặc)
    3. Chuẩn hoá khoảng trắng thừa
    """
    text = str(raw).strip()
    # Bỏ phần ngoặc đơn (có thể chứa chữ hoa, thường, số, ký tự đặc biệt)
    text = re.sub(r'\([A-Za-z0-9\s\.\-\/\,\+\&]+\)', '', text)
    # Bỏ ngoặc đơn lẻ còn sót (ngoặc mở hoặc đóng rời)
    text = text.replace('(', '').replace(')', '')
    text = re.sub(r'\s+', ' ', text).strip()

    # Bỏ đuôi toàn ký tự Latin viết hoa (English noise)
    # CHỈ xóa nếu phần trước đó đã có chữ thường hoặc ký tự có dấu (dấu hiệu tiếng Việt)
    # Tránh xóa nhầm các tên thuần Anh như "COCA COLA CLASSIC"
    has_vietnamese = bool(re.search(r'[a-zà-ỹ]', text))
    if has_vietnamese:
        text = re.sub(r'\s+[A-Z][A-Z0-9\s\.\-\/\,\&]{4,}$', '', text)

    return text.strip()


def _normalize_for_compare(text: str) -> str:
    """
    Chuẩn hoá chuỗi để so sánh fuzzy:
    1. Sửa ký tự OCR lạ (ū→ư, ą→a...)
    2. Bỏ TOÀN BỘ dấu tiếng Việt (để "phô mai" khớp "phomai", "tương" khớp "turong")
    3. Bỏ ký tự đặc biệt, chỉ giữ chữ + số + khoảng trắng
    4. Chuẩn hoá đơn vị: gram→g, lít→l
    """
    # Map ký tự OCR hay nhầm
    replacements = {
        'ū': 'ư', 'ą': 'a', 'ę': 'e', 'ł': 'l', 'ō': 'ơ',
        'å': 'a', 'ń': 'n', 'ś': 's', 'ź': 'z',
    }
    result = text.lower()
    for bad, good in replacements.items():
        result = result.replace(bad, good)

    # Bỏ toàn bộ dấu tiếng Việt bằng Unicode decomposition
    # "phô mai" → "pho mai", "tương cà" → "tuong ca"
    nfkd = unicodedata.normalize('NFKD', result)
    result = ''.join(c for c in nfkd if not unicodedata.combining(c))

    # Đặc biệt: chữ "đ" không bị decompose → thay thủ công
    result = result.replace('đ', 'd')

    # Chuẩn hoá đơn vị trọng lượng
    result = re.sub(r'(\d+)\s*gram\b', r'\1g', result)
    result = re.sub(r'(\d+)\s*lit\b', r'\1l', result)
    result = re.sub(r'(\d+)\s*kg/tui\b', r'\1kg', result)
    result = re.sub(r'\bdura\b', 'dua', result)

    # Chỉ giữ chữ + số + khoảng trắng + dấu chấm (cho trọng lượng như 3.3kg)
    result = re.sub(r'[^a-z0-9\s\.]', '', result)
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def _meaningful_token_overlap(left: str, right: str) -> int:
    stopwords = {"le", "la", "va", "kg", "g", "ml", "hop", "thung", "goi", "cai", "lon"}
    left_tokens = {tok for tok in left.split() if len(tok) >= 3 and tok not in stopwords and not tok.isdigit()}
    right_tokens = {tok for tok in right.split() if len(tok) >= 3 and tok not in stopwords and not tok.isdigit()}
    return len(left_tokens.intersection(right_tokens))


def _build_master_index(data_store: Any) -> Tuple[Dict[str, List[dict]], List[str]]:
    master_entries: Dict[str, List[dict]] = {}
    if data_store:
        if getattr(data_store, "items_by_name", None):
            for items in data_store.items_by_name.values():
                for item_idx, item in enumerate(items):  # C-2: use index for identity-safe check
                    display = item.get("name", "")
                    if not display:
                        continue
                    norm = _normalize_for_compare(display)
                    if not norm:
                        continue
                    master_entries.setdefault(norm, []).append(item)
        elif getattr(data_store, "items_dict", None):
            for item in data_store.items_dict.values():
                display = item.get("name", "")
                if not display:
                    continue
                norm = _normalize_for_compare(display)
                if not norm:
                    continue
                master_entries.setdefault(norm, []).append(item)

    return master_entries, list(master_entries.keys())


def _score_candidate(
    raw_name: str,
    candidate: dict,
    department_hint: str = "",
    unit_hint: str = "",
    price_hint: float | None = None,
    invoice_context: List[str] | None = None,
    supplier_products: str = "",
) -> Tuple[float, float, int]:
    cleaned = _clean_ocr_name(raw_name)
    raw_norm = _normalize_for_compare(cleaned)
    cand_name = candidate.get("name", "") or ""
    cand_norm = _normalize_for_compare(cand_name)

    name_score = 0.0
    if raw_norm and cand_norm:
        raw_tokens = raw_norm.split()
        cand_tokens = cand_norm.split()
        if len(raw_tokens) <= 2 and set(raw_tokens) != set(cand_tokens):
            name_score = fuzz.ratio(raw_norm, cand_norm) / 100.0
        else:
            name_score = fuzz.token_set_ratio(raw_norm, cand_norm) / 100.0
        if len(raw_tokens) > 2 and _meaningful_token_overlap(raw_norm, cand_norm) >= 3:
            name_score = max(name_score, fuzz.partial_token_set_ratio(raw_norm, cand_norm) / 100.0)

    word_count = len(raw_norm.split()) if raw_norm else 0

    dept_score = None
    if department_hint:
        cand_dept = _get_item_department(candidate.get("group", ""))
        dept_score = 1.0 if cand_dept == department_hint else 0.0

    unit_score = None
    if unit_hint:
        cand_unit = candidate.get("unit", "")
        cand_dvt0 = candidate.get("dvt0", "")
        unit_score = 1.0 if (_match_unit(unit_hint, cand_unit) or _match_unit(unit_hint, cand_dvt0)) else 0.0

    price_score = None
    if price_hint is not None:
        price_ref = None
        if unit_hint and _match_unit(unit_hint, candidate.get("unit", "")):
            price_ref = candidate.get("gia_mua")
        elif unit_hint and _match_unit(unit_hint, candidate.get("dvt0", "")):
            price_ref = candidate.get("gia_mua0")
        else:
            price_ref = candidate.get("gia_mua") or candidate.get("gia_mua0")
        try:
            if price_ref is not None:
                price_ref = float(price_ref)
                diff = abs(float(price_hint) - price_ref) / price_ref if price_ref else 1.0
                if diff <= 0.30:
                    price_score = 1.0
                elif diff <= 0.50:
                    price_score = 0.5
                else:
                    price_score = 0.0
        except Exception:
            price_score = 0.0

    context_score = None
    if invoice_context:
        context_norm = _normalize_for_compare(" ".join([str(x) for x in invoice_context if x]))
        cand_tokens = set(cand_norm.split())
        context_tokens = set(context_norm.split())
        if cand_tokens and context_tokens and cand_tokens.intersection(context_tokens):
            context_score = 0.5
        else:
            context_score = 0.0

    supplier_score = None
    if supplier_products:
        supplier_score = 1.0 if cand_name and cand_name.lower() in supplier_products.lower() else 0.0

    weights = {
        "name": 0.45,
        "dept": 0.20,
        "unit": 0.15,
        "price": 0.12,
        "context": 0.05,
        "supplier": 0.03,
    }

    parts = [
        ("name", name_score),
        ("dept", dept_score),
        ("unit", unit_score),
        ("price", price_score),
        ("context", context_score),
        ("supplier", supplier_score),
    ]
    weight_sum = sum(weights[k] for k, v in parts if v is not None)
    if weight_sum <= 0:
        return 0.0, name_score, word_count
    score = sum(weights[k] * v for k, v in parts if v is not None) / weight_sum
    return score, name_score, word_count


def _llm_map_items(
    raw_names: List[str],
    data_store: Any,
    api_key: str,
    department_hint: str = "",
    supplier_code: str = "",
    supplier_products: str = "",
    invoice_context: List[str] = None,
    price_hints: Dict[str, float] = None,   # {raw_name -> unit_price từ hoá đơn}
    candidates_by_item: Dict[str, List[dict]] = None,
) -> Dict[str, str]:
    """
    Bước 2 (Fallback): Gọi LLM cho các item mà fuzzy match không giải quyết được.
    Sử dụng chuỗi suy luận 4 tầng ưu tiên:
      1. Bộ phận (department_hint)   — thu hẹp không gian tìm kiếm
      2. Nhà cung cấp (supplier_code)  — thu hẹp theo nhóm sản phẩm NCC
      3. Sản phẩm mẫu NCC            — prior nghiệp vụ mạnh nhất
      4. Ngữ cảnh chéo (invoice_context) — các mặt hàng khác trong cùng phiếu để phân giải mơ hồ
    """
    if not raw_names or not data_store or not api_key:
        return {}

    if not candidates_by_item:
        logging.error("🚨 [ExcelMapper] LLM Map: Không có candidate shortlist để gọi LLM.")
        return {}

    unique_names = list(set([str(n).strip() for n in raw_names if str(n).strip()]))
    if not unique_names:
        return {}

    # Build Candidate Catalog (shortlist only)
    seen = set()
    catalog_lines = []
    for item_list in candidates_by_item.values():
        for v in item_list:
            name = v.get("name", "")
            if not name:
                continue
            key = (
                name,
                v.get("unit", ""),
                v.get("dvt0", ""),
                v.get("gia_mua"),
                v.get("gia_mua0"),
                v.get("group", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            dvt = v.get("unit", "")
            dvt0 = v.get("dvt0", "")
            gia_mua = v.get("gia_mua")
            gia_mua0 = v.get("gia_mua0")
            dept_label = _get_item_department(v.get("group", "")) or "N/A"
            price_parts = []
            if dvt and gia_mua is not None:
                price_parts.append(f"{dvt}:{int(gia_mua):,}")
            if dvt0 and gia_mua0 is not None:
                price_parts.append(f"{dvt0}:{int(gia_mua0):,}")
            price_str = " | ".join(price_parts)
            line = f"- {name} [Bộ phận: {dept_label}]"
            if dvt:
                line += f" [ĐVT: {dvt}]"
            if dvt0:
                line += f" [DVT0: {dvt0}]"
            if price_str:
                line += f" [Giá: {price_str}]"
            catalog_lines.append(line)
    master_entries = "\n".join(catalog_lines)

    # ------- Xây dựng chuỗi ưu tiên suy luận 3 tầng -------
    # Tầng 1 — BỘ PHẬN
    if department_hint:
        dept_block = (
            f"\n⎣ TẦNG 1 — BỘ PHẬN XÁC ĐỊNH:\n"
            f"Hoá đơn này thuộc bộ phận [{department_hint}].\n"
            f"Hãy ưu tiên các mặt hàng có [Bộ phận: {department_hint}] trong Master List.\n"
            f"Nếu từ điều kiện này không tìm được, mới mở rộng sang bộ phận khác."
        )
    else:
        dept_block = (
            "\n⎣ TẦNG 1 — BỘ PHẬN:\n"
            "Không có thông tin bộ phận. Hãy quan sát [Bộ phận: ...] trong Master List "
            "và chọn nhóm có tính nhất quán (Consistency) cao nhất dựa trên toàn bộ danh sách mặt hàng.\n"
        )

    # Tầng 2 — NHÀ CUNG CẤP
    if supplier_code:
        supplier_block = (
            f"\n⎣ TẦNG 2 — NHÀ CUNG CẤP:\n"
            f"Hoá đơn đến từ NCC mã [{supplier_code}].\n"
        )
    else:
        supplier_block = ""

    # Tầng 3 — SẢN PHẨM MẪU NCC
    if supplier_products:
        products_block = (
            f"\n⎣ TẦNG 3 — MẶT HÀNG ĐIỂN HÌNH CỦA NCC [{supplier_code}]:\n"
            f"{supplier_products}\n"
            f"Đây là ưu tiên nghiệp vụ: nếu tên OCR tương tự các sản phẩm này, ưu tiên match nhóm này trước."
        )
    else:
        products_block = ""

    # Tầng 4 — NGỮ CẢNH CHÉO (toàn bộ phiếu nhập, bao gồm cả các item đang cần map)
    if invoice_context and len(invoice_context) > 1:
        context_block = (
            f"\n⎣ TẦNG 4 — NGỮ CẢNH PHIẾU NHẬP (Cross-Invoice Context):\n"
            f"Toàn bộ phiếu này nhập các mặt hàng: {', '.join(invoice_context)}.\n"
            f"Hãy xét toàn cảnh: các mặt hàng xuất hiện cùng nhau gợi ý chủng loại vật tư của phiếu.\n"
            f"Ví dụ: phiếu có dâu tây, cam, thơm, bơ \u2192 đây là phiếu trái cây, nên 'bơ' = bơ avocado, không phải bơ đậu phụng."
        )
    else:
        context_block = ""

    # Tầng 5 — SO SÁNH GIÁ (chỉ khi có dữ liệu giá từ hoá đơn)
    price_hints = price_hints or {}
    has_price_data = any(v is not None for v in price_hints.values())
    if has_price_data:
        price_block = (
            "\n⎣ TẦNG 5 — SO SÁNH GIÁ (TÍN HIỆU PHỤ — chỉ dùng khi tên không phân giải được):\n"
            "Mỗi item trong Master List có [Giá: ĐVT:giá_tham_chiếu]. Quy tắc so sánh:\n"
            "- Nếu đơn vị trên hoá đơn khớp DVT chính (Gram, Kg, Hộp...) → so với giá DVT chính.\n"
            "- Nếu đơn vị trên hoá đơn khớp DVT0 (Kg, Thùng...) → so với giá DVT0.\n"
            "- Giá hoá đơn sai khác < 30% so với tham chiếu → ưu tiên item đó.\n"
            "- Giá hoá đơn khác biệt quá lớn (> 50%) → giảm điểm ưu tiên cho item đó.\n"
            "- PHỤ: Tên phân giải được rõ ràng → bỏ qua giá; Tên mơ hồ → dùng giá làm tín hiệu phân loại."
        )
    else:
        price_block = ""

    # Tầng 6 — TỪ ĐIỂN ALIAS (Do User xây dựng)
    if hasattr(data_store, 'aliases_dict') and data_store.aliases_dict:
        alias_lines = []
        for al, info in data_store.aliases_dict.items():
            code = info.get("code", "")
            if hasattr(data_store, 'items_by_code') and code in data_store.items_by_code:
                alias_lines.append(f"- '{al}' = {data_store.items_by_code[code]['name']}")
        if alias_lines:
            alias_block = (
                "\n⎣ TẦNG 6 — TỪ ĐIỂN VIẾT TẮT (ALIASES):\n"
                "Nếu tên OCR gần giống (bị lỗi typo/OCR nhẹ) với các từ viết tắt sau, hãy map về tên gốc tương ứng:\n"
                + "\n".join(alias_lines)
            )
        else:
            alias_block = ""
    else:
        alias_block = ""

    # Xây danh sách item cần map kèm shortlist
    items_lines = []
    for n in unique_names:
        cand_names = [c.get("name", "") for c in candidates_by_item.get(n, []) if c.get("name")]
        cand_text = "; ".join(cand_names[:8]) if cand_names else ""
        p = price_hints.get(n)
        price_text = f" [Giá hoá đơn: {int(p):,}]" if p is not None else ""
        items_lines.append(f"- {n}{price_text} | Candidates: {cand_text}")
    items_section = chr(10).join(items_lines)

    prompt = f"""Bạn là chuyên gia chuẩn hóa Danh Mục Vật Tư kho hàng F&B.
Dưới đây là danh sách tên vật tư đọc được từ hoá đơn (có thể viết tắt, sai dấu, lỗi OCR).
Hãy so khớp từng tên với MASTER LIST bằng cách suy luận theo THỨ TỰ ƯU TIÊN sau:
{dept_block}{supplier_block}{products_block}{context_block}{price_block}{alias_block}
⎣ QUY TẮC CHUNG:
- Phải đối chiếu với TOÀN BỘ Master List trước khi quyết định. Không dừng ở kết quả đầu tiên.
- Khi có nhiều kết quả tương đồng, dùng Tầng 4 (ngữ cảnh chéo) và Tầng 5 (giá) để phân giải.
- Chọn kết quả có xác suất đúng cao nhất (Best Probable Match).
- Tên OCR thường bị sai dấu tiếng Việt: "turong" = "tương", "pho mai" = "phomai"
- Bỏ qua phần tiếng Anh trong ngoặc đơn nếu có
- "125g" và "125gram" là CÙNG một sản phẩm; "3.3kg" có thể khớp item không ghi trọng lượng
- Trả về TÊN CHÍNH XÁC TỪ MASTER LIST (copy nguyên văn, KHÔNG kèm [Bộ phận])
- Nếu không chắc >= 60%, trả về ""

 CANDIDATE CATALOG (shortlist only):
 {master_entries}

 VẬT TƯ CẦN MAP (kèm giá + shortlist):
 {items_section}

Trả về JSON thuần (KHÔNG markdown):
{{
    "tên hoá đơn 1": "tên từ MASTER LIST",
    "tên hoá đơn 2": ""
}}
"""
    client = genai.Client(api_key=api_key)
    models_to_try = [
        (data_store.models.get("light_primary"), True),
        (data_store.models.get("light_fallback"), False),
    ]

    def _call_llm(call_prompt: str) -> dict:
        """Gọi LLM và trả về dict kết quả. Ném exception nếu thất bại hoàn toàn."""
        last_error = None
        for model_name, is_primary in models_to_try:
            if not model_name:
                continue
            try:
                global_rate_limiter.wait_if_needed("flash")
                config = None
                if data_store.should_use_minimal_thinking(model_name, is_primary=is_primary):
                    config = types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_budget=0)
                    )
                response = client.models.generate_content(
                    model=model_name,
                    contents=[call_prompt],
                    config=config
                )
                raw = response.text.replace('```json', '').replace('```', '').strip()
                # Robust JSON parse: thử cắt từ { đầu đến } cuối để loại bỏ text thừa
                start = raw.find('{')
                end   = raw.rfind('}')
                if start != -1 and end != -1:
                    raw = raw[start:end + 1]
                return json.loads(raw)
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"LLM Mapping: all models failed — {last_error}")

    def _resolve_llm_keys(input_names: list, raw_result: dict) -> dict:
        """
        Khớp key từ LLM response về đúng input_name gốc.
        LLM đôi khi trả key hơi khác (thêm khoảng trắng, capitalize, bỏ dấu)
        → dùng fuzzy match trên key để tránh silent miss.
        """
        resolved = {}
        used_keys = set()
        for name in input_names:
            # 1. Khớp chính xác (fast path)
            if name in raw_result:
                resolved[name] = raw_result[name]
                used_keys.add(name)
                continue
            # 2. Khớp case-insensitive + strip
            name_lower = name.strip().lower()
            exact_ci = next(
                (k for k in raw_result if k.strip().lower() == name_lower and k not in used_keys),
                None
            )
            if exact_ci:
                resolved[name] = raw_result[exact_ci]
                used_keys.add(exact_ci)
                continue
            # 3. Fuzzy fallback trên key (chỉ dùng khi ≥ 88 để tránh nhầm)
            name_norm = _normalize_for_compare(name)
            best_key, best_score = None, 0
            for k in raw_result:
                if k in used_keys:
                    continue
                score = fuzz.ratio(name_norm, _normalize_for_compare(k))
                if score > best_score:
                    best_score, best_key = score, k
            if best_key and best_score >= 88:
                resolved[name] = raw_result[best_key]
                used_keys.add(best_key)
            else:
                resolved[name] = ""  # Thực sự không có trong response
        return resolved

    try:
        llm_result = _call_llm(prompt)
        resolved   = _resolve_llm_keys(unique_names, llm_result)

        # Retry 1 lần cho các item vẫn còn trống sau lần đầu
        still_missing = [n for n, v in resolved.items() if not v]
        if still_missing and len(still_missing) < len(unique_names):
            # BUG-E6 fix: Xây prompt retry RIÊNG BIỆT (không nối vào prompt gốc
            # vì prompt gốc đã có section VẬT TƯ CẦN MAP → LLM confused 2 danh sách)
            retry_items_text = chr(10).join(f"- {n}" for n in still_missing)
            retry_prompt = f"""Bạn là chuyên gia chuẩn hóa Danh Mục Vật Tư kho hàng F&B.
Lần trước bạn đã bỏ sót {len(still_missing)} vật tư. Hãy cố gắng map lại.
{dept_block}{supplier_block}{products_block}{context_block}{alias_block}
⎣ QUY TẮC: Đối chiếu TOÀN BỘ Master List. Trả TÊN CHÍNH XÁC. Nếu không chắc >= 60%, trả "".

MASTER LIST:
{master_entries}

VẬT TƯ CẦN MAP:
{retry_items_text}

Trả về JSON thuần (KHÔNG markdown):
{{{{
    "tên hoá đơn": "tên từ MASTER LIST"
}}}}
"""
            try:
                retry_result   = _call_llm(retry_prompt)
                retry_resolved = _resolve_llm_keys(still_missing, retry_result)
                for name, val in retry_resolved.items():
                    if val and not resolved.get(name):
                        resolved[name] = val
            except Exception:
                pass  # Retry thất bại — giữ kết quả từ lần đầu

        return resolved

    except Exception as e:
        print(f"LLM Mapping Error (All models failed): {e}")
        return {}


def _infer_department(item_codes: List[str]) -> str:
    """
    Suy ra bộ phận của hoá đơn dựa trên tiền tố của mã vật tư trong items_dict.
    """
    counts = {"BAR": 0, "BEP": 0, "BANH": 0, "RANG": 0}  # BUG-01 fix: thêm RANG
    for code in item_codes:
        c = str(code).upper()
        if c.startswith(("BAR", "RUOU", "CCDC-BAR", "CCDCBAR")):
            counts["BAR"] += 1
        elif c.startswith(("BANH", "CCDC-BANH", "CCDCBANH")):
            counts["BANH"] += 1
        elif c.startswith(("BEP", "CCDC-BEP", "CCDCBEP")):
            counts["BEP"] += 1
        elif c.startswith(("RANG",)):  # BUG-01 fix
            counts["RANG"] += 1
    dominant = max(counts, key=counts.get)
    return dominant if counts[dominant] > 0 else ""


def _resolve_candidate_record(
    raw_name: str,
    mapped_name: str,
    data_store: Any,
    department_hint: str = "",
    unit_hint: str = "",
    price_hint: float | None = None,
    invoice_context: List[str] | None = None,
    supplier_products: str = "",
) -> dict:
    if not mapped_name or not data_store:
        return {}

    candidates = []
    if getattr(data_store, "items_by_name", None):
        candidates = data_store.items_by_name.get(mapped_name.lower(), [])

    if not candidates and getattr(data_store, "items_dict", None):
        fallback = data_store.items_dict.get(mapped_name.lower())
        if fallback:
            return fallback

    if not candidates:
        return {}

    best = None
    best_score = -1.0
    for cand in candidates:
        score, _name_score, _word_count = _score_candidate(
            raw_name=raw_name,
            candidate=cand,
            department_hint=department_hint,
            unit_hint=unit_hint,
            price_hint=price_hint,
            invoice_context=invoice_context,
            supplier_products=supplier_products,
        )
        if score > best_score:
            best_score = score
            best = cand
    return best or {}


def _hybrid_map_items(
    raw_names: List[str],
    data_store: Any,
    api_key: str,
    department_hint: str = "",
    supplier_code: str = "",
    supplier_products: str = "",
    status_callback=None,
    price_hints: Dict[str, float] = None,  # {raw_name -> unit_price từ hoá đơn}
    unit_hints: Dict[str, str] = None,     # {raw_name -> unit từ hoá đơn}
    is_risky: bool = False,
) -> Tuple[Dict[str, str], Dict[str, float]]:
    """
    Pipeline so khớp 2 tầng:
    Tầng 1 — Local scoring (fuzzy + dept + unit + price + context)
    Tầng 2 — LLM fallback (chỉ cho item miss) với shortlist candidates
    """
    if not raw_names:
        return {}, {}

    unique_names = list(set([str(n).strip() for n in raw_names if str(n).strip()]))
    unit_hints = unit_hints or {}
    price_hints = price_hints or {}

    master_entries, master_norm_list = _build_master_index(data_store)
    if not master_entries:
        logging.error("🚨 [ExcelMapper] Master List đang rỗng, không thể map.")
        return {}, {}

    matched: Dict[str, str] = {}
    unmatched: List[str] = []
    score_map: Dict[str, float] = {}
    candidates_by_item: Dict[str, List[dict]] = {}

    map_threshold = 0.82 if is_risky else 0.78
    margin_threshold = 0.15 if is_risky else 0.12

    for raw in unique_names:
        cleaned = _clean_ocr_name(raw)

        # --- BƯỚC 0: KIỂM TRA TỪ ĐIỂN ALIAS ---
        alias_key = cleaned.strip().lower()
        if hasattr(data_store, 'aliases_dict') and alias_key in data_store.aliases_dict:
            alias_info = data_store.aliases_dict[alias_key]
            code = alias_info.get("code", "")
            # Lookup the code to get the standard name
            if hasattr(data_store, 'items_by_code') and code in data_store.items_by_code:
                matched[raw] = data_store.items_by_code[code]["name"]
                score_map[raw] = 1.0
                logging.info(f"[Alias] '{raw}' -> Code: '{code}' ({matched[raw]})")
                continue

        query = _normalize_for_compare(cleaned)
        if not query:
            unmatched.append(raw)
            score_map[raw] = 0.0
            continue

        matches = rfprocess.extract(
            query, master_norm_list,
            scorer=fuzz.token_set_ratio,
            score_cutoff=60,
            limit=25
        )

        candidates = []
        for matched_norm, _score, _ in matches:
            candidates.extend(master_entries.get(matched_norm, []))

        if not candidates:
            unmatched.append(raw)
            score_map[raw] = 0.0
            continue

        scored = []
        for cand in candidates:
            score, name_score, word_count = _score_candidate(
                raw_name=raw,
                candidate=cand,
                department_hint=department_hint,
                unit_hint=unit_hints.get(raw, ""),
                price_hint=price_hints.get(raw),
                invoice_context=unique_names,
                supplier_products=supplier_products,
            )
            scored.append((score, name_score, word_count, cand))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_name_score, best_word_count, best_cand = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0

        candidates_by_item[raw] = [s[3] for s in scored[:8]]
        score_map[raw] = best_score

        if best_word_count <= 2 and best_name_score < 0.88:
            unmatched.append(raw)
            continue

        if best_score >= map_threshold and (best_score - second_score) >= margin_threshold:
            matched[raw] = best_cand.get("name", "")
        else:
            unmatched.append(raw)

    msg = f"[ExcelMapper] Local map: {len(matched)}/{len(unique_names)} khớp. Chưa khớp: {unmatched if unmatched else 'không có'}"
    logging.info(msg)
    if status_callback:
        status_callback(msg)

    # Tầng 2: LLM chỉ cho nhóm chưa khớp, gửi kèm shortlist
    llm_results = {}
    if unmatched and api_key:
        msg_start = f"[ExcelMapper] >>> {len(unmatched)} vat tu chua khop. Khoi dong LLM Fallback..."
        logging.info(msg_start)
        if status_callback:
            status_callback(msg_start)

        llm_results = _llm_map_items(
            unmatched, data_store, api_key,
            department_hint=department_hint,
            supplier_code=supplier_code,
            supplier_products=supplier_products,
            invoice_context=unique_names,
            price_hints=price_hints,
            candidates_by_item={k: v for k, v in candidates_by_item.items() if k in unmatched},
        )
        matched_by_llm = sum(1 for v in llm_results.values() if v)
        still_empty = sum(1 for v in llm_results.values() if not v)
        for item_name, mapped_to in llm_results.items():
            result_str = mapped_to if mapped_to else "[Không tìm thấy]"
            item_msg = f"[ExcelMapper] LLM: '{item_name}' => '{result_str}'"
            logging.info(item_msg)
            if status_callback:
                status_callback(item_msg)
        summary_msg = (
            f"[ExcelMapper] LLM kết quả: {matched_by_llm}/{len(unmatched)} map được"
            + (f" | {still_empty} vẫn trống (tô vàng)" if still_empty else "")
        )
        logging.info(summary_msg)
        if status_callback:
            status_callback(summary_msg)
    elif unmatched:
        msg_warn = f"[ExcelMapper] {len(unmatched)} vat tu chua khop nhung khong co API Key de chay LLM Fallback."
        logging.warning(msg_warn)
        if status_callback:
            status_callback(msg_warn)

    final = {}
    for name in unique_names:
        if name in matched:
            final[name] = matched[name]
        elif name in llm_results and llm_results[name]:
            final[name] = llm_results[name]
            score_map[name] = max(score_map.get(name, 0.0), 0.70)
        else:
            final[name] = ""

    return final, score_map
