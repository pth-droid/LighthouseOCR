"""
Comprehensive regression test for all fixes in this session.
Run: python test_all_fixes.py
"""
import sys, copy
sys.path.insert(0, '.')

PASS = 0
FAIL = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f" | {detail}" if detail else ""))

print("=" * 60)
print("LIGHTHOUSE OCR — REGRESSION TEST SUITE")
print("=" * 60)

# ─── FIX-1: _row_has_math_error (Case 4: qty>0, price=0) ──────────
print("\n[FIX-1] _row_has_math_error — zero-price detection")
from core_excel_mapper import _row_has_math_error

check("qty=2 up=0 total=0 -> error",      _row_has_math_error({"quantity":2,"unit_price":0,"total_price":0}))
check("qty=0 up=0 total=0 -> no error",   not _row_has_math_error({"quantity":0,"unit_price":0,"total_price":0}))
check("qty=2 up=50000 total=100000 -> ok",not _row_has_math_error({"quantity":2,"unit_price":50000,"total_price":100000}))
check("qty=2 up=50000 total=99999 -> ok (within 5d tolerance)", not _row_has_math_error({"quantity":2,"unit_price":50000,"total_price":99999}))
check("qty=2 up=50000 total=110000 -> error", _row_has_math_error({"quantity":2,"unit_price":50000,"total_price":110000}))
check("qty=0 total=50000 -> error (OCR miss qty)", _row_has_math_error({"quantity":0,"unit_price":0,"total_price":50000}))
check("non-numeric -> error",              _row_has_math_error({"quantity":"abc","unit_price":0,"total_price":0}))

# ─── FIX-2 + H-4: qty=1 fallback, normalized qty in merged_item ───
print("\n[FIX-2+H-4] _normalize_pricing_basis — missing qty/unit_price")
from module_calculator import _normalize_pricing_basis

raw1 = {
    "items": [{"product_name": "Bơ lạt", "quantity": None, "unit_price": None, "total_price": 85000}],
    "transaction_info": {"department": "BEP"},
    "totals": {"total_amount": 85000},
    "supplier_info": {"supplier_name_code": "NCC01"},
}
result1 = _normalize_pricing_basis(copy.deepcopy(raw1), copy.deepcopy(raw1))
item1 = result1["items"][0]
check("FIX-2: qty fallback = 1",    item1.get("quantity") == 1,    f"got {item1.get('quantity')}")
check("H-4:  unit_price = total",   item1.get("unit_price") == 85000, f"got {item1.get('unit_price')}")
check("FIX-2: total preserved",     item1.get("payable_total") == 85000, f"got {item1.get('payable_total')}")

# ─── FIX-4: discrepancy warning khi tổng phiếu tay lệch >5% ──────
print("\n[FIX-4] discrepancy warning — handwritten total mismatch")
raw2 = {
    "items": [
        {"product_name": "Cam", "quantity": 5, "unit_price": 20000, "total_price": 100000},
        {"product_name": "Bưởi", "quantity": 3, "unit_price": 30000, "total_price": 90000},
    ],
    "transaction_info": {},
    "totals": {"total_amount": 150000},  # Đúng là 190000, chênh lệch ~21%
    "supplier_info": {"supplier_name_code": ""},
}
result2 = _normalize_pricing_basis(copy.deepcopy(raw2), copy.deepcopy(raw2))
warn = result2.get("totals", {}).get("total_discrepancy_warning", "")
check("FIX-4: warning exists when >5% divergence", bool(warn), f"warn='{warn[:60]}'")
check("FIX-4: warning contains CANH BAO",  "CẢNH BÁO" in warn or "CANH BAO" in warn.upper())

raw3 = copy.deepcopy(raw2)
raw3["totals"]["total_amount"] = 191000  # Sát đúng -> không cảnh báo
result3 = _normalize_pricing_basis(raw3, copy.deepcopy(raw3))
warn3 = result3.get("totals", {}).get("total_discrepancy_warning", "")
check("FIX-4: NO warning when within 5%", not warn3, f"unexpected warn='{warn3[:40]}'")

# ─── H-1: No double discount ──────────────────────────────────────
print("\n[H-1] No double-discount when both % and amount present")
raw4 = {
    "items": [{"product_name": "Đường", "quantity": 10, "unit_price": 20000, "total_price": 200000}],
    "transaction_info": {
        "raw_discount_info": "CK 10% và giảm thêm 5,000 cho đơn từ 100,000",
        "raw_shipping_fee_info": "",
        "raw_payment_method": "",
    },
    "totals": {},
    "supplier_info": {"supplier_name_code": "NCC01"},
}
result4 = _normalize_pricing_basis(copy.deepcopy(raw4), copy.deepcopy(raw4))
item4 = result4["items"][0]
# Với 10% CK: discount = 20,000; payable = 180,000
# Nếu bị double (+ 5,000): discount = 25,000; payable = 175,000
check("H-1: discount only 10% (not 10% + 5000)",
    item4.get("discount_amount") == 20000,
    f"discount={item4.get('discount_amount')}")

# ─── C-1: VAT voting bỏ qua FIX-2 fallback items ─────────────────
print("\n[C-1] VAT-inclusive voting skips FIX-2 fallback items")
raw5 = {
    "items": [
        # Item bình thường có đủ VAT data
        {"product_name": "Trà", "quantity": 5, "unit_price": 10000, "total_price": 55000, "raw_vat_amount": 5000},
        # Item FIX-2 fallback: không có qty/unit_price
        {"product_name": "Cà phê", "quantity": None, "unit_price": None, "total_price": 30000, "raw_vat_amount": 3000},
    ],
    "transaction_info": {},
    "totals": {},
    "supplier_info": {"supplier_name_code": "NCC01"},
}
# Chỉ kiểm tra không crash và FIX-2 item được xử lý
result5 = _normalize_pricing_basis(copy.deepcopy(raw5), copy.deepcopy(raw5))
check("C-1: no crash with mixed items", len(result5.get("items", [])) == 2)
check("C-1: fallback item qty=1",
    result5["items"][1].get("quantity") == 1,
    f"qty={result5['items'][1].get('quantity')}")

# ─── M-1: confidence default 1.0 ─────────────────────────────────
print("\n[M-1] _is_mapping_risky — parse-fail defaults to 1.0 (not risky)")
from core_excel_mapper import _is_mapping_risky, _is_high_risk

inv_str_conf = {"document_info": {"confidence_score": "PRO_FALLBACK", "invoice_type": "PRINTED", "recommended_model": ""}}
risky = _is_mapping_risky(inv_str_conf)
check("M-1: string confidence -> not risky by default", not risky, f"risky={risky}")

# _is_high_risk: parse-fail -> confidence=1.0 (not high by confidence alone)
# Note: supplier_code trống vẫn -> high_risk. Test đúng semantics: confidence string không trigger.
inv_str_with_supplier = {
    "document_info": {"confidence_score": "HIGH_CONF_STRING"},  # không parse được -> 1.0
    "supplier_info": {"supplier_name_code": "NCC01"},           # supplier có mã -> không trigger NCC check
}
high = _is_high_risk(inv_str_with_supplier)
check("_is_high_risk: string confidence + supplier OK -> not high_risk", not high, f"high={high}")

# ─── Unit-in-Name: regex nâng cấp ────────────────────────────────
print("\n[UNIT-IN-NAME] Regex + dairy 1ml=1g")
from core_excel_mapper import _extract_size_from_name, _try_size_in_name_conversion, _is_dairy_liquid

regex_cases = [
    ("sua tuoi meiji 950ml",      950.0, "ml"),
    ("Sữa tươi Meiji 950 ml",     950.0, "ml"),   # space
    ("Phô mai dairymont 2kg",     2.0,   "kg"),
    ("Nước Lavie 1,5L",           1.5,   "L"),    # comma decimal
    ("Nước Lavie 1.5 lít",        1.5,   "L"),    # lít accent
    ("Kem sữa tươi 500cc",        500.0, "ml"),   # cc->ml
    ("Bột cacao 200 gram",        200.0, "g"),
    ("Sữa Vinamilk 2L",           2.0,   "L"),
    ("Thịt bò (không có kích thước)", None, ""),
]
for name, ev, eu in regex_cases:
    v, u = _extract_size_from_name(name)
    check(f"extract '{name}'", v == ev and u == eu, f"got ({v},{u}) want ({ev},{eu})")

# Dairy detection
check("_is_dairy_liquid('Sữa tươi Meiji')", _is_dairy_liquid("Sữa tươi Meiji"))
check("_is_dairy_liquid('Vinamilk')",        _is_dairy_liquid("Vinamilk"))
check("NOT dairy: 'Nước cam Tropicana'",     not _is_dairy_liquid("Nước cam Tropicana"))

# Case A: same-dimension (phô mai 2kg / gói -> kg)
m_phomai = {"unit": "kg", "dvt0": ""}
q, up, u, note, warn = _try_size_in_name_conversion("Phô mai dairymont 2kg", "gói", m_phomai, 3, 250000)
check("Case-A: 3 gói ×2kg = 6kg",  q == 6.0 and u == "kg", f"q={q} u={u}")
check("Case-A: up = 250000/2",      up == 125000.0, f"up={up}")
check("Case-A: note contains 'Quy doi'", "Quy đổi" in note or "Quy" in note)

# Case B: dairy 1ml=1g (sữa 950ml / hộp -> gram)
m_sua = {"unit": "gram", "dvt0": "kg"}
q2, up2, u2, note2, warn2 = _try_size_in_name_conversion("sua tuoi meiji 950ml", "hộp", m_sua, 5, 45000)
check("Case-B dairy: 5 hộp ×950g = 4750g", q2 == 4750.0 and u2 == "gram", f"q={q2} u={u2}")
check("Case-B dairy: note contains '1ml=1g'", "1ml=1g" in note2, f"note={note2}")

# Case B: dairy 1L=1kg (Vinamilk 2L / hộp -> kg)
m_vin = {"unit": "kg", "dvt0": ""}
q3, up3, u3, note3, warn3 = _try_size_in_name_conversion("Sữa Vinamilk 2L", "hộp", m_vin, 10, 32000)
check("Case-B dairy 2L: 10 hộp ×2kg = 20kg", q3 == 20.0 and u3 == "kg", f"q={q3} u={u3}")

# Case C: non-dairy volume vs weight -> warn only
m_cam = {"unit": "gram", "dvt0": ""}
q4, up4, u4, note4, warn4 = _try_size_in_name_conversion("Nước cam Tropicana 1L", "hộp", m_cam, 5, 20000)
check("Case-C: non-dairy -> no auto-convert", q4 is None)
check("Case-C: UNIT_IN_NAME warning", "UNIT_IN_NAME" in warn4, f"warn={warn4[:60]}")

# ─── Summary ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"RESULT: {PASS}/{total} passed | {FAIL} failed")
if FAIL == 0:
    print("ALL TESTS PASSED")
else:
    print(f"WARNING: {FAIL} tests FAILED — review above")
print("=" * 60)
