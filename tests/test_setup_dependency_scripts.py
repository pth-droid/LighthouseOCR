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

    def test_deploy_build_captures_noisy_structure_preflight_output(self):
        text = _read("Deploy_Build.ps1")

        self.assertIn("function Invoke-NativeToLog", text)
        self.assertIn("RedirectStandardError", text)
        self.assertIn("$PreflightLog", text)
        self.assertIn("Get-Content -LiteralPath $PreflightLog", text)
        self.assertIn("PP-StructureV3 runtime check OK.", text)
        self.assertNotIn("*> $PreflightLog", text)

    def test_deploy_build_retries_pyinstaller_resource_lock_failures(self):
        text = _read("Deploy_Build.ps1")

        self.assertIn("function Invoke-PyInstallerBuildWithRetry", text)
        self.assertIn("pyinstaller_attempt_", text)
        self.assertIn("PyInstaller failed on attempt", text)
        self.assertIn("Start-Sleep", text)

    def test_deploy_build_can_fallback_when_windows_resource_update_is_blocked(self):
        deploy_text = _read("Deploy_Build.ps1")
        spec_text = _read("LighthouseOCR.spec")

        self.assertIn("function Test-WindowsResourceUpdate", deploy_text)
        self.assertIn("LHOCR_SKIP_WIN_RESOURCE_UPDATE", deploy_text)
        self.assertIn("LHOCR_SKIP_WIN_RESOURCE_UPDATE", spec_text)
        self.assertIn("remove_all_resources", spec_text)
        self.assertIn("write_manifest_to_executable", spec_text)

    def test_deploy_build_does_not_delete_locked_runtime_env_before_copy(self):
        text = _read("Deploy_Build.ps1")

        self.assertNotIn("Remove-Item -LiteralPath $BuildOutputDir -Recurse -Force", text)
        self.assertIn("/XD __pycache__", text)
        self.assertIn("/XF *.pyc *.pyo", text)

    def test_deploy_build_uses_alternate_output_when_existing_exe_is_locked(self):
        text = _read("Deploy_Build.ps1")

        self.assertIn("LighthouseOCR_locked_", text)
        self.assertIn("Existing app output is locked", text)

    def test_deploy_build_suppresses_robocopy_percent_progress_noise(self):
        text = _read("Deploy_Build.ps1")

        self.assertIn("/NP", text)

    def test_structure_runner_exposes_check_mode(self):
        text = _read("ocr_structure_runner.py")

        self.assertIn("def run_check(", text)
        self.assertIn('--check', text)


if __name__ == "__main__":
    unittest.main()
