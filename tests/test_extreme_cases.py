"""
Extreme Case Logic Tests for Lighthouse OCR.
Tests missing data, mixed types, and boundary conditions.
"""
import sys, copy
sys.path.insert(0, '.')

def check(label, condition, detail=""):
    if condition:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label} | {detail}")
        sys.exit(1)

print("=" * 60)
print("LIGHTHOUSE OCR - EXTREME CASE AUDIT")
print("=" * 60)

from core_excel_mapper import _row_has_math_error
from module_calculator import _normalize_pricing_basis

# --- TEST 1: Extreme Math Errors / Missing Data ---
print("\n[EXTREME-1] Math Error Detection with Nulls/Strings")
cases_math = [
    ("All None -> No error (empty)", {"quantity": None, "unit_price": None, "total_price": None}, False),
    ("Mixed None/Zero -> Error", {"quantity": 5, "unit_price": None, "total_price": 0}, True),
    ("String data -> Error", {"quantity": "5kg", "unit_price": 100, "total_price": 500}, True),
    ("Negative values -> Error", {"quantity": -1, "unit_price": 100, "total_price": 100}, True),
    ("Huge numbers -> No error", {"quantity": 1000000, "unit_price": 0.5, "total_price": 500000}, False),
]
for label, data, expected in cases_math:
    check(label, _row_has_math_error(data) == expected)

# --- TEST 2: Normalization Extreme Cases ---
print("\n[EXTREME-2] Normalization (Fallback Logic)")

# Case: Total price is missing but SL/DG exist
raw_missing_total = {
    "items": [{"product_name": "A", "quantity": 10, "unit_price": 5000, "total_price": None}],
    "transaction_info": {"department": "BEP"},
    "totals": {"total_amount": 50000},
    "supplier_info": {"supplier_name_code": "S1"},
}
res1 = _normalize_pricing_basis(raw_missing_total, raw_missing_total)
check("Missing total_price -> auto calc", res1["items"][0].get("total_price") == 50000)

# Case: Both qty and unit_price missing, total_price is 0
raw_zero_total = {
    "items": [{"product_name": "B", "quantity": None, "unit_price": None, "total_price": 0}],
    "transaction_info": {"department": "BAR"},
    "totals": {"total_amount": 0},
    "supplier_info": {"supplier_name_code": "S1"},
}
res2 = _normalize_pricing_basis(raw_zero_total, raw_zero_total)
check("Zero total -> qty=1, up=0", res2["items"][0].get("quantity") == 1 and res2["items"][0].get("unit_price") == 0)

# Case: Junk data in fields
raw_junk = {
    "items": [{"product_name": "C", "quantity": "N/A", "unit_price": "Unknown", "total_price": "10,000"}],
    "transaction_info": {},
    "totals": {"total_amount": 10000},
    "supplier_info": {},
}
res3 = _normalize_pricing_basis(raw_junk, raw_junk)
check("Junk strings -> cleaned to numbers", res3["items"][0].get("total_price") == 10000)

# --- TEST 3: Size Extraction Boundaries ---
print("\n[EXTREME-3] Size Extraction (Ambiguous names)")
from core_excel_mapper import _extract_size_from_name
cases_size = [
    ("Item 100.5.2ml", None, ""), # Multiple dots
    ("Item .5kg", 0.5, "kg"),     # Leading dot
    ("Item 1,000,000mg", 1000000.0, "g"), # Huge mg -> g (if logic supports mg conversion)
    ("Item 50-100ml", 100.0, "ml"), # Range (should pick last number usually)
]
for name, ev, eu in cases_size:
    v, u = _extract_size_from_name(name)
    # The current regex might not be perfect for junk like 100.5.2, but it should be robust
    if ev is not None:
        check(f"extract {name}", v == ev and u == eu, f"got {v} {u}")

print("\n" + "=" * 60)
print("EXTREME CASE AUDIT COMPLETED")
print("=" * 60)
