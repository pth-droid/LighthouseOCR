import unittest

from business_kie import BusinessKIE


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


if __name__ == "__main__":
    unittest.main()
