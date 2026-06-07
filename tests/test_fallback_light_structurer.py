import unittest

from fallback_light_structurer import build_light_fallback_text, should_use_light_fallback


class FallbackLightStructurerTests(unittest.TestCase):
    def test_should_use_light_fallback_when_validation_fails(self):
        self.assertTrue(should_use_light_fallback({"can_use_local_result": False}))
        self.assertFalse(should_use_light_fallback({"can_use_local_result": True}))

    def test_build_light_fallback_text_includes_structure_context(self):
        text = build_light_fallback_text({
            "raw_text": "Cafe\nTong cong 250000",
            "regions": [{"label": "table", "bbox": [1, 2, 3, 4]}],
            "tokens": [{"text": "Cafe", "confidence": 0.9}],
        })

        self.assertIn("RAW_TEXT", text)
        self.assertIn("REGIONS", text)
        self.assertIn("TOKENS", text)
        self.assertIn("Cafe", text)


if __name__ == "__main__":
    unittest.main()
