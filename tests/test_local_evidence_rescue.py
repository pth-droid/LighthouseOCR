import unittest

from local_evidence_rescue import (
    apply_rescue_evidence,
    extract_supplier_candidates_from_text,
    should_rescue_supplier,
)


class FakeDataStore:
    suppliers_dict = {
        "NLAM": "Cong ty TNHH TM & XNK Nhat Lam",
        "HRUOU": "Cong Ty TNHH Ham Ruou Viet Nam Chi Nhanh Da Nang",
    }


class LocalEvidenceRescueTests(unittest.TestCase):
    def test_extracts_supplier_from_company_header_text(self):
        text = "CONG TY TNHH THUONG MAI & XUAT NHAP KHAU NHAT LAM\nPHIEU XUAT KHO"

        candidates = extract_supplier_candidates_from_text(text, FakeDataStore(), "header_crop")

        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["code"], "NLAM")
        self.assertEqual(candidates[0]["source"], "header_crop")
        self.assertGreaterEqual(candidates[0]["confidence"], 0.85)

    def test_rejects_salesperson_line_as_supplier_evidence(self):
        text = "Ten NVBH: Hien HRC DN"

        candidates = extract_supplier_candidates_from_text(text, FakeDataStore(), "full_text")

        self.assertEqual(candidates, [])

    def test_supplier_rescue_needed_when_supplier_missing_or_suspicious(self):
        self.assertTrue(should_rescue_supplier({
            "supplier_info": {"supplier_name_code": None, "supplier_name_raw": None}
        }))
        self.assertTrue(should_rescue_supplier({
            "supplier_info": {"supplier_name_code": "HRUOU", "supplier_name_raw": "Hin HRC DN"}
        }))

    def test_apply_supplier_rescue_sets_metadata(self):
        invoice = {"supplier_info": {"supplier_name_code": None, "supplier_name_raw": None}}
        rescue = {
            "supplier_candidates": [{
                "code": "NLAM",
                "raw_text": "CONG TY TNHH TM XNK NHAT LAM",
                "confidence": 0.92,
                "source": "header_crop",
            }]
        }

        updated = apply_rescue_evidence(invoice, rescue)

        self.assertEqual(updated["supplier_info"]["supplier_name_code"], "NLAM")
        self.assertEqual(updated["_local_evidence_rescue"]["supplier"]["source"], "header_crop")


if __name__ == "__main__":
    unittest.main()
