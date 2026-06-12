import inspect
import unittest

import ocr_pipeline_structure as ops


class RunPipelineDeptTests(unittest.TestCase):
    def test_apply_override_wins_over_ocr_department(self):
        j = {"transaction_info": {"department": "BAR"}}   # OCR-guessed
        ops._apply_department_override(j, "BEP")           # user tag
        self.assertEqual(j["transaction_info"]["department"], "BEP")
        self.assertEqual(j["_department_source"], "user_tag")

    def test_escalation_gate_decision_matches_predicate(self):
        garbled = {
            "document_info": {"invoice_type": "VAT_INVOICE"},
            "transaction_info": {"invoice_number": "X", "invoice_date": "2026-01-01"},
            "items": [{"product_name": n} for n in ["cāB", "B'd", "10Hinh"]],
            "totals": {},
        }
        self.assertTrue(ops._should_escalate_weak_result(garbled, {"confidence": 0.86}))

        clean = {
            "document_info": {"invoice_type": "VAT_INVOICE"},
            "transaction_info": {"invoice_number": "DO-1", "invoice_date": "2026-01-01"},
            "items": [{"product_name": "Ba rọi xông khói Tasany 3mm"}],
            "totals": {},
        }
        self.assertFalse(ops._should_escalate_weak_result(clean, {"confidence": 0.95}))

    def test_run_pipeline_accepts_dept_map_kwarg(self):
        sig = inspect.signature(ops.run_pipeline)
        self.assertIn("dept_map", sig.parameters)
        self.assertIsNone(sig.parameters["dept_map"].default)


if __name__ == "__main__":
    unittest.main()
