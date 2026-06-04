import unittest
import subprocess

from module_paddle_structure_ocr import StructurePaddleOCREngine


class StructurePaddleOCREngineTests(unittest.TestCase):
    def test_completion_message_includes_engine_and_time(self):
        engine = StructurePaddleOCREngine()
        message = engine._build_completion_message(
            block_count=12,
            avg_confidence=0.875,
            elapsed_seconds=1.234,
        )
        self.assertIn("PP-StructureV3", message)
        self.assertIn("12", message)
        self.assertIn("87.5%", message)
        self.assertIn("1.23s", message)

    def test_build_result_summary_is_compact(self):
        engine = StructurePaddleOCREngine()
        result = engine._build_result_summary({
            "pages": [{"a": 1}],
            "raw_text": "A",
            "avg_confidence": 0.9,
            "elapsed_seconds": 2.0,
        })
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["avg_confidence"], 0.9)
        self.assertEqual(result["raw_text"], "A")

    def test_subprocess_options_do_not_deadlock_or_show_console(self):
        engine = StructurePaddleOCREngine()

        options = engine._build_popen_kwargs(stderr_target=subprocess.DEVNULL)

        self.assertIs(options["stdout"], subprocess.DEVNULL)
        self.assertIsNot(options["stderr"], subprocess.PIPE)
        self.assertIn("startupinfo", options)
        if subprocess.STARTUPINFO is not None:
            self.assertIsNotNone(options["startupinfo"])

    def test_subprocess_environment_removes_pyinstaller_python_vars(self):
        engine = StructurePaddleOCREngine()
        env = engine._build_subprocess_env({
            "PYTHONHOME": "bad",
            "PYTHONPATH": "bad",
            "KEEP_ME": "ok",
        })

        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertEqual(env["KEEP_ME"], "ok")

    def test_subprocess_has_timeout_to_avoid_infinite_freeze(self):
        engine = StructurePaddleOCREngine()

        self.assertGreaterEqual(engine.subprocess_timeout_seconds, 60)


if __name__ == "__main__":
    unittest.main()
