import unittest

from invoice_json_builder import build_invoice_json
from invoice_validation import validate_invoice_json


class StructureInvoiceJsonTests(unittest.TestCase):
    def test_build_invoice_json_matches_downstream_schema(self):
        invoice = build_invoice_json(
            kie_result={
                "supplier": {
                    "supplier_name_code": "COHA",
                    "supplier_name_raw": "Co Ha Tap Hoa",
                    "confidence": 0.9,
                },
                "transaction": {"department": "BEP"},
                "items": [{
                    "product_name": "Ca rot baby",
                    "unit": "Gram",
                    "quantity": 1,
                    "unit_price": 250000,
                    "total_price": 250000,
                }],
                "totals": {"total_amount": 250000},
                "warnings": [],
            },
            confidence_score=0.88,
        )

        self.assertEqual(invoice["supplier_info"]["supplier_name_code"], "COHA")
        self.assertEqual(invoice["transaction_info"]["department"], "BEP")
        self.assertEqual(invoice["items"][0]["product_name"], "Ca rot baby")
        self.assertEqual(invoice["totals"]["total_amount"], 250000)

    def test_validation_passes_when_supplier_item_and_total_exist(self):
        invoice = build_invoice_json(
            kie_result={
                "supplier": {
                    "supplier_name_code": "COHA",
                    "supplier_name_raw": "Co Ha Tap Hoa",
                    "confidence": 0.9,
                },
                "transaction": {"department": "BEP"},
                "items": [{
                    "product_name": "Ca rot baby",
                    "unit": "Gram",
                    "quantity": 1,
                    "unit_price": 250000,
                    "total_price": 250000,
                }],
                "totals": {"total_amount": 250000},
                "warnings": [],
            },
            confidence_score=0.88,
        )

        report = validate_invoice_json(invoice)

        self.assertTrue(report["can_use_local_result"])
        self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
