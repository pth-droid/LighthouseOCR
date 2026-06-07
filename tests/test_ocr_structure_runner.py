import unittest

import ocr_structure_runner


class OcrStructureRunnerTests(unittest.TestCase):
    def test_make_safe_json_removes_non_serializable_values(self):
        data = {
            "text": "Cafe",
            "score": 0.91,
            "array_like": object(),
            "nested": {"value": 10},
        }

        safe = ocr_structure_runner._make_safe_json(data)

        self.assertEqual(safe["text"], "Cafe")
        self.assertEqual(safe["score"], 0.91)
        self.assertEqual(safe["nested"], {"value": 10})
        self.assertIsInstance(safe["array_like"], str)

    def test_build_output_has_required_top_level_keys(self):
        output = ocr_structure_runner._build_output([], elapsed_seconds=1.25)

        self.assertIn("pages", output)
        self.assertIn("raw_text", output)
        self.assertIn("avg_confidence", output)
        self.assertIn("elapsed_seconds", output)
        self.assertEqual(output["elapsed_seconds"], 1.25)

    def test_output_has_no_debug_image_fields(self):
        output = ocr_structure_runner._build_output([
            {"res": {"input_img": [[[1, 2, 3]]], "rec_texts": ["Cafe"]}}
        ], elapsed_seconds=0.1)
        text = str(output).lower()
        self.assertNotIn("image_base64", text)
        self.assertNotIn("outputimages", text)
        self.assertNotIn("input_img", text)

    def test_format_runtime_error_explains_missing_paddlex_ocr_extra(self):
        message = ocr_structure_runner._format_runtime_error(
            RuntimeError("PP-StructureV3 requires additional dependencies")
        )

        self.assertIn("paddlex[ocr]", message)
        self.assertIn("Setup_Moi_Truong.bat", message)


if __name__ == "__main__":
    unittest.main()
