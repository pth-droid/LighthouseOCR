import unittest

from module_paddle_ocr import LocalPaddleOCREngine


class ModulePaddleOcrTests(unittest.TestCase):
    def test_build_start_message_includes_runtime_version(self):
        engine = LocalPaddleOCREngine()
        message = engine._build_start_message("3.6.0")
        self.assertIn("PaddleOCR 3.6.0", message)

    def test_build_completion_message_includes_version_and_total_time(self):
        engine = LocalPaddleOCREngine()
        message = engine._build_completion_message(
            runtime_version="3.6.0",
            text_count=12,
            avg_confidence=0.875,
            elapsed_seconds=1.234,
        )
        self.assertIn("PaddleOCR 3.6.0", message)
        self.assertIn("12 dòng", message)
        self.assertIn("87.5%", message)
        self.assertIn("1.23s", message)


if __name__ == "__main__":
    unittest.main()
