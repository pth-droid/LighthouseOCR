import unittest

from business_kie import BusinessKIE, _parse_totals


class FakeDataStore:
    suppliers_dict = {"COHA": "Co Ha Tap Hoa"}
    aliases_dict = {"ca rot baby": {"code": "VT001", "units": [{"unit": "Gram", "factor": 1}]}}
    items_by_code = {
        "vt001": {"code": "VT001", "name": "Ca rot baby", "unit": "Gram", "group": "BEP"}
    }
    items_dict = {}


class BusinessKIETests(unittest.TestCase):
    def test_extracts_supplier_and_alias_item_from_master_data(self):
        result = BusinessKIE(FakeDataStore()).extract({
            "raw_text": "Co Ha Tap Hoa\nCa rot baby\nTong cong 250000"
        })

        self.assertEqual(result["supplier"]["supplier_name_code"], "COHA")
        self.assertEqual(result["items"][0]["item_code"], "VT001")
        self.assertEqual(result["transaction"]["department"], "BEP")

    def test_parse_totals_ignores_phone_numbers_and_prefers_total_line(self):
        totals = _parse_totals(
            "Dien thoai : 0762746491\n"
            "616,656.00\n"
            "Thue VAT:\n"
            "665,988.48\n"
            "TONG TIEN THANH TOAN:"
        )

        self.assertEqual(totals["total_amount"], 665988.48)

    def test_parse_totals_ignores_portal_number_when_total_has_no_separator(self):
        totals = _parse_totals(
            "So: 873457 - Portal: 862539\n"
            "Tien thue GTGT:\n"
            "604.714\n"
            "Tong tien thanh toan"
        )

        self.assertEqual(totals["total_amount"], 604714.0)


if __name__ == "__main__":
    unittest.main()
