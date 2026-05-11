import re
import logging
from typing import Any


# ---- Đơn vị tính aliases (dùng cho quy đổi DVT0 → DVT) ----
# Group các cách viết khác nhau cùng chỉ một đơn vị
_UNIT_ALIAS_GROUPS = [
    {"kg", "kilogram", "kilo", "kgs"},
    {"gram", "gr", "g", "gam"},
    {"lít", "lit", "liter", "litre", "l"},
    {"ml", "mililit", "cc"},
    {"hộp", "hop", "box", "h.p"},
    {"lon", "can", "l.n"},
    {"chai", "bottle", "chai/c"},
    {"gói", "goi", "pack", "túi"},
    {"thùng", "thung", "carton", "ctn"},
    {"cái", "cai", "piece", "pcs"},
    {"cuộn", "cuon", "roll"},
]


def _match_unit(invoice_unit: str, master_dvt0: str) -> bool:
    """
    Kiểm tra xem đơn vị trên hoá đơn có tương đương Dvt0 trong Master List không.
    Hỗ trợ các cách viết khác nhau (kg/Kg/KG, hộp/Hop/box, ...).
    """
    if not invoice_unit or not master_dvt0:
        return False
    u1 = invoice_unit.strip().lower()
    u2 = master_dvt0.strip().lower()
    if u1 == u2:
        return True
    for group in _UNIT_ALIAS_GROUPS:
        if u1 in group and u2 in group:
            return True
    return False


def _extract_size_from_name(name: str):
    """
    Trích xuất kích thước/trọng lượng/thể tích ghi trong tên mặt hàng.
    Trả về (value: float, unit_str: str) hoặc (None, "") nếu không tìm thấy.

    Hỗ trợ:
      - Có hoặc không có khoảng trắng: "950ml", "950 ml", "1.5 L", "1,5L"
      - Số thập phân với dấu phẩy hoặc chấm: "1,5L" → 1.5L
      - Tiếng Việt: "lít", "lít", "gam", "ki-lô-gam"
      - Đơn vị thể tích: ml, cc, L, lít, litre, liter
      - Đơn vị khối lượng: g, gr, gam, gram, mg, kg, kgs, oz, lb, pound
    Ví dụ:
      "Sữa tươi Meiji 950ml"    → (950.0, "ml")
      "Sữa tươi Meiji 950 ml"   → (950.0, "ml")
      "Phô mai dairymont 2kg"   → (2.0,   "kg")
      "Nước Lavie 1,5L"         → (1.5,   "L")
      "Nước Lavie 1.5 lít"      → (1.5,   "L")
      "Kem sữa 500cc"           → (500.0, "ml")  # cc → ml
      "Bơ Anchor 500g"          → (500.0, "g")
      "Bột cacao 200 gram"      → (200.0, "g")
    """
    # Mỗi pattern: (regex, canonical_unit)
    # Thứ tự quan trọng: đơn vị dài hơn phải đứng trước để tránh partial match
    # VD: "kg" phải trước "g" để "2kg" không bị đọc nhầm là "2k" + "g"
    patterns = [
        # ── Thể tích ──
        (r'(\d+(?:[.,]\d+)?)\s*cc\b',                          'ml'),   # cc ≡ ml
        (r'(\d+(?:[.,]\d+)?)\s*ml\b',                          'ml'),
        (r'(\d+(?:[.,]\d+)?)\s*(?:lít|lít|litre|liter|lit)\b', 'L'),   # tiếng Việt có dấu + không dấu
        (r'(\d+(?:[.,]\d+)?)\s*L\b',                           'L'),   # viết hoa (1L, 2L)
        # ── Khối lượng ──
        (r'(\d+(?:[.,]\d+)?)\s*(?:kg|kgs?|ki.?lô.?gam)\b',   'kg'),  # kg, kgs, ki-lô-gam
        (r'(\d+(?:[.,]\d+)?)\s*(?:mg)\b',                      'mg'),
        (r'(\d+(?:[.,]\d+)?)\s*(?:gram|gam|gr)\b',             'g'),   # dài hơn trước "g"
        (r'(\d+(?:[.,]\d+)?)\s*g\b',                           'g'),   # đứng sau để tránh "mg" bị bắt
        (r'(\d+(?:[.,]\d+)?)\s*(?:pound|lb)\b',                'lb'),
        (r'(\d+(?:[.,]\d+)?)\s*oz\b',                          'oz'),
    ]
    name_str = str(name or "")
    for pat, unit_key in patterns:
        m = re.search(pat, name_str, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(',', '.'))
                if val > 0:
                    return val, unit_key
            except ValueError:
                continue
    return None, ""


# Map đơn vị volume/weight về nhóm để so sánh dimension
_VOLUME_UNITS = {"ml", "l", "lít", "lit", "liter", "litre", "cc"}
_WEIGHT_UNITS = {"g", "gr", "gam", "gram", "mg", "kg", "kgs", "oz", "lb", "pound"}

# Từ khoá nhận dạng sản phẩm sữa nước
# Lighthouse áp dụng quy ước 1ml = 1g cho nhóm này (mật độ sữa ≈ 1.03 g/ml, làm tròn = 1)
_DAIRY_LIQUID_KEYWORDS = [
    "sữa", "sua", "milk", "sữa tươi", "sữa hộp", "sữa lon",
    "sữa đặc", "sữa không đường", "sữa ít béo", "sữa nguyên kem",
    "fresh milk", "whole milk", "skim milk",
    # Phổ biến tại Lighthouse:
    "meiji", "vinamilk", "dalat milk", "meadow fresh", "greenfields",
    "anchor milk", "dutch lady", "friso", "similac",
]


def _is_dairy_liquid(name: str) -> bool:
    """
    Nhận dạng sản phẩm sữa nước.
    Lighthouse áp dụng quy ước 1ml ≈ 1g cho nhóm này.
    """
    name_lower = name.lower()
    return any(kw in name_lower for kw in _DAIRY_LIQUID_KEYWORDS)


def _convert_volume_to_weight_dairy(size_val: float, size_unit: str, target_dvt: str) -> float | None:
    """
    Quy đổi thể tích → khối lượng cho sản phẩm sữa nước.
    Quy ước Lighthouse: 1ml = 1g, 1L = 1kg.

    Args:
        size_val:   Giá trị kích thước (VD: 950, 1.5)
        size_unit:  Đơn vị trong tên hàng ("ml", "L", "cc", ...)
        target_dvt: Đơn vị kho trong Master List ("gram", "g", "kg", ...)

    Returns:
        Giá trị đã quy đổi sang target_dvt, hoặc None nếu không áp dụng được.
    """
    su = size_unit.lower().strip()
    tu = (target_dvt or "").lower().strip()

    # Bước 1: Chuẩn hoá size về ml
    if su in {"ml", "cc"}:
        size_ml = size_val
    elif su in {"l", "lít", "lít", "lit", "liter", "litre"}:
        size_ml = size_val * 1000
    else:
        return None  # Không phải volume → không áp dụng

    # Bước 2: Chuyển ml → target_dvt
    if tu in {"g", "gr", "gram", "gam"}:
        return size_ml          # 1ml = 1g
    elif tu in {"kg", "kgs"}:
        return size_ml / 1000   # 1ml = 0.001kg
    return None


def _convert_same_dimension(size_val: float, size_unit: str, target_dvt: str) -> float | None:
    su = size_unit.lower().strip()
    tu = (target_dvt or "").lower().strip()

    if su in _VOLUME_UNITS and tu in _VOLUME_UNITS:
        size_ml = size_val
        if su in {"l", "lít", "lit", "liter", "litre"}:
            size_ml = size_val * 1000

        if tu in {"ml", "cc"}:
            return size_ml
        elif tu in {"l", "lít", "lit", "liter", "litre"}:
            return size_ml / 1000

    elif su in _WEIGHT_UNITS and tu in _WEIGHT_UNITS:
        size_g = size_val
        if su in {"kg", "kgs", "ki-lô-gam"}:
            size_g = size_val * 1000
        elif su in {"mg"}:
            size_g = size_val / 1000

        if tu in {"g", "gr", "gram", "gam"}:
            return size_g
        elif tu in {"kg", "kgs"}:
            return size_g / 1000
        elif tu in {"mg"}:
            return size_g * 1000

    return None


def _try_size_in_name_conversion(
    raw_name: str,
    invoice_unit: str,
    master_record: dict,
    qty: Any,
    unit_price: Any,
):
    """
    Thử quy đổi đơn vị khi đơn vị hoá đơn không khớp DVT/DVT0 nhưng tên
    mặt hàng chứa kích thước.

    Trả về (qty_final, unit_price_final, unit_final, conversion_note, warning_note)
    hoặc (None, None, "", "", warning/empty) nếu không thể tự động quy đổi.

    Luồng xử lý:
    1. Trích xuất (size_val, size_unit) từ tên hàng
    2. Case A — same dimension: size_unit khớp DVT/DVT0 → quy đổi trực tiếp
       VD: "Phô mai 2kg" / gói → DVT=kg → 1 gói = 2kg
    3. Case B — dairy exception: volume vs weight nhưng là sữa tươi
       VD: "Sữa Meiji 950ml" / hộp → DVT=gram → 1 hộp = 950g (1ml=1g)
    4. Case C — khác dimension, không phải dairy → [UNIT_IN_NAME] warning
    """
    size_val, size_unit = _extract_size_from_name(raw_name)
    if not size_val or not size_unit:
        return None, None, "", "", ""

    master_dvt  = master_record.get("unit", "")
    master_dvt0 = master_record.get("dvt0", "")

    try:
        orig_qty = float(qty) if qty is not None else None
        orig_up  = float(unit_price) if unit_price is not None else None
    except (TypeError, ValueError):
        orig_qty = orig_up = None

    su = size_unit.lower()
    is_volume = su in _VOLUME_UNITS
    is_weight = su in _WEIGHT_UNITS

    # ── Phân loại dimension ───────────────────────────────────────────────────
    tu = (master_dvt or "").lower()
    size_dim = "volume" if is_volume else ("weight" if is_weight else "unknown")
    dvt_dim  = "volume" if tu in _VOLUME_UNITS else ("weight" if tu in _WEIGHT_UNITS else "other")

    # ── Case A: Cùng dimension (metric conversion) hoặc khớp đơn vị ───────────
    # Quy đổi thẳng về master_dvt nếu cùng hệ (volume/weight)
    if size_dim != "unknown" and size_dim == dvt_dim:
        converted_val = _convert_same_dimension(size_val, size_unit, master_dvt)
        if converted_val is not None and converted_val > 0 and orig_qty is not None:
            new_qty = round(orig_qty * converted_val, 3)
            new_up  = round(orig_up / converted_val, 4) if orig_up is not None else None
            note = (
                f"[Quy đổi DVT từ tên: {orig_qty} {invoice_unit} "
                f"\u00d7 {converted_val:g}{master_dvt} (từ {size_val:g}{size_unit}) = {new_qty:g} {master_dvt}]"
            )
            return new_qty, new_up, master_dvt, note, ""

    # Nếu không cùng dimension nhưng size_unit khớp DVT0 (ví dụ: hộp -> thùng, cần he_so0)
    if master_dvt0 and _match_unit(size_unit, master_dvt0) and orig_qty is not None and size_val > 0:
        new_qty = orig_qty * size_val
        new_up  = orig_up / size_val if orig_up is not None else None

        he_so0_raw = master_record.get("he_so0")
        if he_so0_raw:
            try:
                hs = float(he_so0_raw)
                if hs > 0:
                    final_qty = round(new_qty * hs, 3)
                    final_up = round(new_up / hs, 4) if new_up else None
                    note = (
                        f"[Quy đổi DVT từ tên & kho: {orig_qty} {invoice_unit} "
                        f"\u00d7 {size_val:g}{size_unit} \u00d7 {hs:g} = {final_qty:g} {master_dvt}]"
                    )
                    return final_qty, final_up, master_dvt, note, ""
            except ValueError:
                pass

    # ── Case B: dairy exception — volume vs weight ────────────────────────────
    # Lighthouse quy ước: 1ml = 1g cho sữa tươi
    # VD: "Sữa Meiji 950ml" / hộp → DVT=gram → 1 hộp = 950g
    if size_dim == "volume" and dvt_dim == "weight" and _is_dairy_liquid(raw_name):
        converted = _convert_volume_to_weight_dairy(size_val, size_unit, master_dvt)
        if converted is not None and converted > 0 and orig_qty is not None:
            new_qty = round(orig_qty * converted, 3)
            new_up  = round(orig_up / converted, 4) if orig_up is not None else None
            note = (
                f"[Quy đổi DVT sữa (1ml=1g): {orig_qty} {invoice_unit} "
                f"\u00d7 {converted:g}{master_dvt} = {new_qty:g} {master_dvt}]"
            )
            return new_qty, new_up, master_dvt, note, ""

    # ── Case C: khác dimension, không phải dairy → cảnh báo thủ công ─────────
    if size_dim != dvt_dim:
        warning = (
            f"[UNIT_IN_NAME: {size_val:g}{size_unit}/{invoice_unit} — "
            f"dimension {size_dim} vs DVT '{master_dvt}' ({dvt_dim}), "
            f"cần quy đổi thủ công]"
        )
        return None, None, "", "", warning

    return None, None, "", "", ""
