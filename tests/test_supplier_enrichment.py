import unittest

from supplier_enrichment import enrich_supplier


class FakeDataStore:
    suppliers_dict = {
        "COHA": "Co Ha Tap Hoa",
        "DAIRY": "Dairy House",
    }
    suppliers_context_str = (
        "COHA=Co Ha Tap Hoa (San pham: Dau an, Gas mini, Ngu vi) | "
        "DAIRY=Dairy House (San pham: Sua, Bo, Pho mai)"
    )


class SupplierEnrichmentTests(unittest.TestCase):
    def test_infers_missing_supplier_from_multiple_item_evidence(self):
        invoice = {
            "supplier_info": {"supplier_name_code": None, "supplier_name_raw": None},
            "items": [
                {"product_name": "Dau an"},
                {"product_name": "Gas mini"},
                {"product_name": "Ngu vi"},
            ],
        }

        enriched = enrich_supplier(invoice, FakeDataStore())

        self.assertEqual(enriched["supplier_info"]["supplier_name_code"], "COHA")
        self.assertEqual(enriched["supplier_info"]["supplier_name_raw"], "Co Ha Tap Hoa")
        self.assertEqual(enriched["_supplier_resolution"]["source"], "item_inference")
        self.assertGreaterEqual(enriched["_supplier_resolution"]["confidence"], 0.8)
        self.assertIn("Dau an", enriched["_supplier_resolution"]["evidence"])

    def test_does_not_infer_supplier_from_weak_single_item_evidence(self):
        invoice = {
            "supplier_info": {"supplier_name_code": None, "supplier_name_raw": None},
            "items": [{"product_name": "Sua"}],
        }

        enriched = enrich_supplier(invoice, FakeDataStore())

        self.assertIsNone(enriched["supplier_info"]["supplier_name_code"])
        self.assertEqual(enriched["_supplier_resolution"]["source"], "unknown")
        self.assertLess(enriched["_supplier_resolution"]["confidence"], 0.7)

    def test_preserves_supplier_read_directly_from_invoice(self):
        invoice = {
            "supplier_info": {
                "supplier_name_code": "DAIRY",
                "supplier_name_raw": "Dairy House",
            },
            "items": [{"product_name": "Dau an"}],
        }

        enriched = enrich_supplier(invoice, FakeDataStore())

        self.assertEqual(enriched["supplier_info"]["supplier_name_code"], "DAIRY")
        self.assertEqual(enriched["_supplier_resolution"]["source"], "ocr_header")

    def test_rejects_salesperson_line_as_supplier_even_when_code_is_known(self):
        invoice = {
            "supplier_info": {
                "supplier_name_code": "DAIRY",
                "supplier_name_raw": "Hin HRC DN",
            },
            "items": [{"product_name": "Unknown"}],
        }

        enriched = enrich_supplier(invoice, FakeDataStore())

        self.assertIsNone(enriched["supplier_info"]["supplier_name_code"])
        self.assertEqual(enriched["_supplier_resolution"]["source"], "unknown")


if __name__ == "__main__":
    unittest.main()
