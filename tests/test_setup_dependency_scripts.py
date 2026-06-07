import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class SetupDependencyScriptsTests(unittest.TestCase):
    def test_setup_scripts_install_structure_pipeline_dependencies(self):
        required = [
            "paddlepaddle-gpu",
            '"paddlepaddle==3.2.0"',
            "https://www.paddlepaddle.org.cn/packages/stable/cpu/",
            '"numpy<2.0.0"',
            '"paddleocr[doc-parser]==3.6.0"',
            '"paddlex[ocr]==3.6.1"',
        ]

        for script_name in ("Setup_Moi_Truong.bat", "Setup_Nguon.bat"):
            text = _read(script_name)
            for needle in required:
                with self.subTest(script=script_name, dependency=needle):
                    self.assertIn(needle, text)

    def test_setup_scripts_verify_pp_structure_runner_after_install(self):
        for script_name in ("Setup_Moi_Truong.bat", "Setup_Nguon.bat"):
            text = _read(script_name)
            with self.subTest(script=script_name):
                self.assertIn("ocr_structure_runner.py", text)
                self.assertIn("--check", text)

    def test_deploy_build_verifies_structure_pipeline_before_packaging_env(self):
        text = _read("Deploy_Build.ps1")

        self.assertIn("ocr_structure_runner.py", text)
        self.assertIn("--check", text)

    def test_structure_runner_exposes_check_mode(self):
        text = _read("ocr_structure_runner.py")

        self.assertIn("def run_check(", text)
        self.assertIn('--check', text)


if __name__ == "__main__":
    unittest.main()
