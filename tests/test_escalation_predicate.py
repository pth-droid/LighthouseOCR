import unittest

from ocr_pipeline_structure import (
    _is_garbled_name,
    _garbled_name_ratio,
    _has_total_mismatch,
    _looks_handwritten,
    _should_escalate_after_calc,
    _should_escalate_weak_result,
)


def _inv(items=None, invoice_type="VAT_INVOICE", number="X1", date="2026-05-23",
         total_warning=None):
    j = {
        "document_info": {"invoice_type": invoice_type},
        "transaction_info": {"invoice_number": number, "invoice_date": date},
        "items": [{"product_name": n} for n in (items or [])],
        "totals": {},
    }
    if total_warning:
        j["totals"]["total_discrepancy_warning"] = total_warning
    return j


class EscalationPredicateTests(unittest.TestCase):
    def test_is_garbled_name_flags_junk(self):
        # Unambiguous garble: punctuation, leading digit, <=2 letters, no vowel.
        # (Phonotactically-invalid-but-vowel-bearing fragments like "xutg" are an
        # accepted miss — the ratio threshold + handwritten/total-mismatch signals
        # are the backstops.)
        for bad in ["cāB", "B'd", "10Hinh", 'chuo"', "", "B", "tng"]:
            self.assertTrue(_is_garbled_name(bad), bad)

    def test_is_garbled_name_accepts_legit(self):
        for ok in ["BO XAY", "UC GA", "Ba rọi xông khói Tasany 3mm",
                   "Khoai tây Hychoice AAA XLF straight cut 1kg", "NAM"]:
            self.assertFalse(_is_garbled_name(ok), ok)

    def test_garbled_ratio_r12_like_over_threshold(self):
        names = ["chua", "Mam", "cāB", "Bap", "chio", "pau",
                 "Duo Bi", "xutg", "B'd", "10Hinh"]
        self.assertGreaterEqual(_garbled_name_ratio(_inv(names)), 0.30)

    def test_garbled_ratio_clean_printed_is_zero(self):
        names = ["Ba rọi xông khói Tasany 3mm",
                 "Khoai tây Hychoice AAA XLF straight cut 1kg"]
        self.assertEqual(_garbled_name_ratio(_inv(names)), 0.0)

    def test_total_mismatch_detected(self):
        self.assertTrue(_has_total_mismatch(_inv(total_warning="[CẢNH BÁO: lệch 80%]")))
        self.assertFalse(_has_total_mismatch(_inv()))

    def test_looks_handwritten_by_type_or_missing_header(self):
        self.assertTrue(_looks_handwritten(_inv(invoice_type="HANDWRITTEN_INVOICE")))
        self.assertTrue(_looks_handwritten(_inv(invoice_type="RETAIL_INVOICE")))
        self.assertTrue(_looks_handwritten(_inv(number="", date="")))
        self.assertFalse(_looks_handwritten(_inv(invoice_type="VAT_INVOICE")))

    def test_escalate_true_for_weak_cases(self):
        r12 = _inv(["cāB", "xutg", "B'd", "10Hinh", "chua"], invoice_type="VAT_INVOICE")
        self.assertTrue(_should_escalate_weak_result(r12, {"confidence": 0.86}))
        r10 = _inv(["cad", "Nam"], invoice_type="HANDWRITTEN_INVOICE",
                   total_warning="[CẢNH BÁO]")
        self.assertTrue(_should_escalate_weak_result(r10, {"confidence": 0.865}))
        hw = _inv(["Cà chua", "Bắp"], invoice_type="HANDWRITTEN_INVOICE")
        self.assertTrue(_should_escalate_weak_result(hw, {"confidence": 0.86}))

    def test_escalate_false_for_clean_printed(self):
        printed = _inv(["Ba rọi xông khói Tasany 3mm",
                        "Khoai tây Hychoice AAA XLF straight cut 1kg"],
                       invoice_type="VAT_INVOICE", number="DO-1", date="2026-05-23")
        self.assertFalse(_should_escalate_weak_result(printed, {"confidence": 0.881}))


class EscalateAfterCalcTests(unittest.TestCase):
    def _post_calc(self, warning=None, already_pro=False):
        j = {"items": [{}], "totals": {}, "_structure_pipeline": {}}
        if warning:
            j["totals"]["total_discrepancy_warning"] = warning
        if already_pro:
            j["_structure_pipeline"]["pro_vision_fallback_used"] = True
        return j

    def test_escalates_on_total_mismatch(self):
        self.assertTrue(_should_escalate_after_calc(self._post_calc(warning="[CẢNH BÁO]")))

    def test_no_escalation_without_mismatch(self):
        self.assertFalse(_should_escalate_after_calc(self._post_calc()))

    def test_no_re_escalation_when_already_pro_vision(self):
        # Handwritten invoices already went to Pro Vision — don't loop.
        self.assertFalse(
            _should_escalate_after_calc(self._post_calc(warning="[CẢNH BÁO]", already_pro=True))
        )


if __name__ == "__main__":
    unittest.main()
