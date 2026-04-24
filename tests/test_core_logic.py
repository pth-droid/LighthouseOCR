"""
Comprehensive regression test for all fixes.
ASCII ONLY to avoid Windows encoding issues.
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
print("LIGHTHOUSE OCR - REGRESSION TEST")
print("=" * 60)

# FIX-1
print("\n[FIX-1] _row_has_math_error")
from core_excel_mapper import _row_has_math_error
check("qty=2 up=0 total=0 -> error",      _row_has_math_error({"quantity":2,"unit_price":0,"total_price":0}))
check("qty=0 up=0 total=0 -> no error",   not _row_has_math_error({"quantity":0,"unit_price":0,"total_price":0}))

# FIX-2
print("\n[FIX-2] _normalize_pricing_basis")
from module_calculator import _normalize_pricing_basis
raw1 = {
    "items": [{"product_name": "Test", "quantity": None, "unit_price": None, "total_price": 85000}],
    "transaction_info": {"department": "BEP"},
    "totals": {"total_amount": 85000},
    "supplier_info": {"supplier_name_code": "NCC01"},
}
result1 = _normalize_pricing_basis(copy.deepcopy(raw1), copy.deepcopy(raw1))
item1 = result1["items"][0]
check("qty fallback = 1", item1.get("quantity") == 1)
check("unit_price = total", item1.get("unit_price") == 85000)

# Regex sizes
print("\n[REGEX] Size extraction")
from core_excel_mapper import _extract_size_from_name
cases = [
    ("Meiji 950ml", 950.0, "ml"),
    ("Dairymont 2kg", 2.0, "kg"),
    ("Lavie 1.5L", 1.5, "L")
]
for name, ev, eu in cases:
    v, u = _extract_size_from_name(name)
    check(f"extract {name}", v == ev and u == eu, f"got {v} {u}")

print("\n" + "=" * 60)
print("ALL CORE LOGIC TESTS PASSED (ASCII SAFE)")
print("=" * 60)
