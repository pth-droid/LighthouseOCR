import copy
import unittest

from module_calculator import _normalize_pricing_basis, _snap_vat_rate


def _calc(raw):
    return _normalize_pricing_basis(copy.deepcopy(raw), copy.deepcopy(raw))


class SnapVatRateTests(unittest.TestCase):
    def test_snaps_exact_standard_rates(self):
        self.assertEqual(_snap_vat_rate(0.0), 0.0)
        self.assertEqual(_snap_vat_rate(5.0), 5.0)
        self.assertEqual(_snap_vat_rate(8.0), 8.0)
        self.assertEqual(_snap_vat_rate(10.0), 10.0)

    def test_snaps_within_tolerance(self):
        # rounding noise on clean amounts stays within +/- 0.5pp
        self.assertEqual(_snap_vat_rate(7.9997), 8.0)
        self.assertEqual(_snap_vat_rate(5.4), 5.0)
        self.assertEqual(_snap_vat_rate(0.3), 0.0)
        self.assertEqual(_snap_vat_rate(9.6), 10.0)

    def test_rejects_non_standard_rates(self):
        # r23 item-1 misread: 52,080 / 908,020 = 5.74% -> not a real rate
        self.assertIsNone(_snap_vat_rate(5.74))
        self.assertIsNone(_snap_vat_rate(7.3))
        self.assertIsNone(_snap_vat_rate(6.0))


class RelabelVatRateTests(unittest.TestCase):
    def test_amount_overrides_wrong_llm_rate_label(self):
        # r10_125908 "Bò xay": amount 48,750 on base 975,000 == 5%, LLM said 8%.
        raw = {
            "items": [{
                "product_name": "Bò xay", "quantity": 5,
                "unit_price": 195000, "total_price": 975000,
                "raw_vat_rate": "8%", "raw_vat_amount": 48750,
            }],
            "transaction_info": {},
            "totals": {"total_amount": 1023750},
            "supplier_info": {"supplier_name_code": "BPHUC"},
        }
        result = _calc(raw)
        item = result["items"][0]
        self.assertEqual(item["vat_rate"], 5.0)
        self.assertEqual(item["vat_amount"], 48750)
        self.assertFalse(result["totals"].get("total_discrepancy_warning"))


def _r23_like():
    # Bách Phúc Phương 20260528_145917: light fallback grabbed VAT for only the
    # first line (52,080 lifted from row 2's line total -> 5.74% of base) and
    # left the other three with no VAT. The self-consistent (but wrong) total
    # means Signal 1 cannot catch it; Signal 2 (non-standard rate) must.
    return {
        "items": [
            {"product_name": "Ức gà", "quantity": 10.94, "unit_price": 83000,
             "total_price": 908020, "raw_vat_rate": "8%", "raw_vat_amount": 52080},
            {"product_name": "Xương gà", "quantity": 4.96, "unit_price": 10000,
             "total_price": 49600},
            {"product_name": "Khoai tây múi cau", "quantity": 1, "unit_price": 150000,
             "total_price": 150000},
            {"product_name": "Ba chỉ bò cuộn", "quantity": 1, "unit_price": 220000,
             "total_price": 220000},
        ],
        "transaction_info": {"raw_payment_method": "TM"},
        "totals": {"total_amount": 1379700},  # consistent with the wrong lines
        "supplier_info": {"supplier_name_code": "BPHUCPHUONG"},
    }


class VatInconsistencyTests(unittest.TestCase):
    def test_r23_nonstandard_rate_raises_warning(self):
        result = _calc(_r23_like())
        warn = result["totals"].get("total_discrepancy_warning", "")
        self.assertTrue(warn, "expected a reconciliation warning for r23")
        self.assertIn("CẢNH BÁO", warn)
        self.assertTrue(result["items"][0].get("_vat_inconsistent"))

    def test_delivery_note_zero_vat_no_warning(self):
        # r3 Sáng Ngọc (TM/CK delivery note): no VAT anywhere -> nothing to flag.
        raw = {
            "items": [
                {"product_name": "Ba rọi xông khói Tasany", "quantity": 10,
                 "unit_price": 167000, "total_price": 1670000},
                {"product_name": "Khoai tây Hychoice", "quantity": 10,
                 "unit_price": 55000, "total_price": 550000},
            ],
            "transaction_info": {"raw_payment_method": "TM/CK"},
            "totals": {"total_amount": 2220000},
            "supplier_info": {"supplier_name_code": "SNGOC"},
        }
        result = _calc(raw)
        self.assertFalse(result["totals"].get("total_discrepancy_warning"))
        self.assertIsNone(result["items"][0].get("_vat_inconsistent"))


class TotalDivergenceTests(unittest.TestCase):
    def _vat_invoice(self, declared_total):
        # VAT 8% line whose rate snaps cleanly (no per-line inconsistency), so
        # only the declared-vs-computed total divergence can trip the guard.
        return {
            "items": [{"product_name": "X", "quantity": 10, "unit_price": 100000,
                       "total_price": 1000000, "raw_vat_rate": "8%",
                       "raw_vat_amount": 80000}],
            "transaction_info": {},
            "totals": {"total_amount": declared_total},  # computed = 1,080,000
            "supplier_info": {"supplier_name_code": "NCC"},
        }

    def test_vat_invoice_over_one_percent_warns(self):
        result = _calc(self._vat_invoice(1100000))  # 1.82% off, 20,000đ
        self.assertIn("CẢNH BÁO", result["totals"].get("total_discrepancy_warning", ""))

    def test_vat_invoice_within_one_percent_silent(self):
        result = _calc(self._vat_invoice(1090000))  # 0.92% off, 10,000đ (> floor)
        self.assertFalse(result["totals"].get("total_discrepancy_warning"))


if __name__ == "__main__":
    unittest.main()
