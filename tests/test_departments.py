import unittest

from departments import VALID_DEPARTMENTS, department_prompt_line


class DepartmentsTests(unittest.TestCase):
    def test_valid_departments_exact_set(self):
        self.assertEqual(VALID_DEPARTMENTS, ("BEP", "BAR", "BANH", "RANG"))

    def test_prompt_line_for_valid_dept_mentions_dept(self):
        line = department_prompt_line("BEP")
        self.assertIn("BEP", line)
        self.assertIn("bộ phận", line.lower())
        self.assertTrue(line.endswith("\n\n"))

    def test_prompt_line_normalizes_case_and_whitespace(self):
        self.assertIn("BAR", department_prompt_line("  bar "))

    def test_prompt_line_empty_for_invalid_dept(self):
        self.assertEqual(department_prompt_line("XYZ"), "")
        self.assertEqual(department_prompt_line(""), "")
        self.assertEqual(department_prompt_line(None), "")


if __name__ == "__main__":
    unittest.main()
