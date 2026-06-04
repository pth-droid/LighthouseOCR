import unittest

from module_calculator import _should_skip_llm


class CalculatorSupplierResolutionTests(unittest.TestCase):
    def test_missing_supplier_no_longer_forces_calculator_llm(self):
        raw_json = {
            "supplier_info": {"supplier_name_code": None},
            "items": [{"product_name": "Dau an", "quantity": 1, "unit_price": 1000}],
        }

        self.assertTrue(_should_skip_llm(raw_json))


if __name__ == "__main__":
    unittest.main()
