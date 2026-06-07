import unittest

from core_excel_mapper import _score_candidate as excel_score_candidate
from item_matcher import _score_candidate as item_score_candidate


class ItemMatcherTests(unittest.TestCase):
    def test_ocr_dura_typo_matches_coconut_cream_candidate(self):
        raw = "Nuoc cot dura Le mejor 400ml hopx24 hop thung"
        candidate = {"name": "Nước cốt dừa Vietcoco", "unit": "Gram", "group": "LH-BEP"}

        item_score, item_name_score, _ = item_score_candidate(raw, candidate)
        excel_score, excel_name_score, _ = excel_score_candidate(raw, candidate)

        self.assertGreaterEqual(item_name_score, 0.95)
        self.assertGreaterEqual(item_score, 0.95)
        self.assertGreaterEqual(excel_name_score, 0.95)
        self.assertGreaterEqual(excel_score, 0.95)

    def test_short_generic_name_does_not_get_partial_token_boost(self):
        raw = "bao"
        candidate = {"name": "Bao tay nilong", "unit": "Cai", "group": "LH-BEP"}

        item_score, item_name_score, _ = item_score_candidate(raw, candidate)
        excel_score, excel_name_score, _ = excel_score_candidate(raw, candidate)

        self.assertLess(item_name_score, 0.95)
        self.assertLess(item_score, 0.95)
        self.assertLess(excel_name_score, 0.95)
        self.assertLess(excel_score, 0.95)


if __name__ == "__main__":
    unittest.main()
