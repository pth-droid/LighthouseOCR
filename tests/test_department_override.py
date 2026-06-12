import unittest

from ocr_pipeline_structure import _apply_department_override


class DepartmentOverrideTests(unittest.TestCase):
    def test_sets_department_and_source(self):
        j = {}
        _apply_department_override(j, "BEP")
        self.assertEqual(j["transaction_info"]["department"], "BEP")
        self.assertEqual(j["_department_source"], "user_tag")

    def test_normalizes_case(self):
        j = {"transaction_info": {}}
        _apply_department_override(j, " bar ")
        self.assertEqual(j["transaction_info"]["department"], "BAR")

    def test_invalid_dept_ignored(self):
        j = {"transaction_info": {"department": "OLD"}}
        _apply_department_override(j, "XYZ")
        self.assertEqual(j["transaction_info"]["department"], "OLD")
        self.assertNotIn("_department_source", j)

    def test_none_ignored(self):
        j = {}
        _apply_department_override(j, None)
        self.assertEqual(j, {})

    def test_idempotent_and_reappliable_on_fresh_json(self):
        j1 = {}
        _apply_department_override(j1, "RANG")
        _apply_department_override(j1, "RANG")
        self.assertEqual(j1["transaction_info"]["department"], "RANG")
        j2 = {"transaction_info": {"department": None}}
        _apply_department_override(j2, "RANG")
        self.assertEqual(j2["transaction_info"]["department"], "RANG")


if __name__ == "__main__":
    unittest.main()
