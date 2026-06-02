import sys
import types
import unittest
from unittest.mock import patch

import ocr_runner


class OcrRunnerTests(unittest.TestCase):
    def _build_v3_engine_with_mode(self, runtime_mode):
        captured = {}

        class FakePaddleOCR:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        fake_module = types.SimpleNamespace(__version__="3.6.0", PaddleOCR=FakePaddleOCR)

        with patch.dict(
            sys.modules,
            {
                "paddleocr": fake_module,
            },
            clear=False,
        ):
            ocr, engine_mode = ocr_runner._build_ocr_engine(runtime_mode)

        return ocr, engine_mode, captured

    def test_v3_engine_disables_mkldnn_on_cpu(self):
        ocr, engine_mode, captured = self._build_v3_engine_with_mode("stable")
        self.assertEqual(engine_mode, "v3")
        self.assertIsNotNone(ocr)
        self.assertEqual(captured.get("device"), "cpu")
        self.assertFalse(captured.get("enable_mkldnn", True))

    def test_v3_engine_enables_mkldnn_in_cpu_fast_mode(self):
        _, _, captured = self._build_v3_engine_with_mode("cpu_fast")
        self.assertEqual(captured.get("device"), "cpu")
        self.assertTrue(captured.get("enable_mkldnn"))

    def test_v3_engine_uses_gpu_when_requested(self):
        _, _, captured = self._build_v3_engine_with_mode("gpu")
        self.assertEqual(captured.get("device"), "gpu")
        self.assertFalse(captured.get("enable_mkldnn", True))

    def test_v3_runtime_falls_back_to_stable_cpu_when_fast_mode_fails(self):
        init_modes = []

        class FakePaddleOCR:
            def __init__(self, **kwargs):
                self.mode = "gpu" if kwargs.get("device") == "gpu" else ("cpu_fast" if kwargs.get("enable_mkldnn") else "stable")
                init_modes.append(self.mode)

            def predict(self, image_path):
                if self.mode == "cpu_fast":
                    raise RuntimeError("oneDNN crash")
                return [{"image_path": image_path, "mode": self.mode}]

        fake_module = types.SimpleNamespace(__version__="3.6.0", PaddleOCR=FakePaddleOCR)

        with patch.dict(sys.modules, {"paddleocr": fake_module}, clear=False):
            result = ocr_runner._run_v3_ocr_with_fallback("sample.jpg", "cpu_fast")

        self.assertEqual([item["mode"] for item in result], ["stable"])
        self.assertEqual(init_modes, ["cpu_fast", "stable"])


if __name__ == "__main__":
    unittest.main()
