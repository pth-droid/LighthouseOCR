import unittest

from structure_result_normalizer import normalize_structure_result


class StructureResultNormalizerTests(unittest.TestCase):
    def test_normalize_extracts_tokens_regions_and_tables(self):
        normalized = normalize_structure_result({
            "raw_text": "Cafe\nTong cong 250000",
            "avg_confidence": 0.91,
            "pages": [{
                "res": {
                    "rec_texts": ["Cafe", "Tong cong"],
                    "rec_scores": [0.9, 0.92],
                    "layout_det_res": {
                        "boxes": [{"label": "table", "coordinate": [1, 2, 3, 4]}]
                    },
                    "table_res_list": [{"html": "<table></table>"}],
                }
            }],
        })

        self.assertEqual(normalized["raw_text"], "Cafe\nTong cong 250000")
        self.assertEqual(len(normalized["tokens"]), 2)
        self.assertEqual(normalized["regions"][0]["label"], "table")
        self.assertEqual(len(normalized["tables"]), 1)


if __name__ == "__main__":
    unittest.main()
