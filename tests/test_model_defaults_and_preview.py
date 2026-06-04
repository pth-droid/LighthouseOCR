import os
import tempfile
import unittest

from data_manager import DataManager, format_model_option, model_id_from_display
from post_process_dialog import _resolve_invoice_image_path


RETIRED_OR_UNSAFE_DEFAULTS = {
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-flash-lite-preview-09-2025",
    "gemini-3.1-flash-lite-preview",
}


class ModelDefaultsAndPreviewTests(unittest.TestCase):
    def test_runtime_defaults_do_not_use_retired_preview_models(self):
        manager = DataManager()

        defaults = set(manager.models.values())

        self.assertTrue(defaults.isdisjoint(RETIRED_OR_UNSAFE_DEFAULTS))

    def test_load_config_replaces_retired_preview_models(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = DataManager()
            manager.config_file = os.path.join(tmp_dir, "lighthouse_config.json")
            with open(manager.config_file, "w", encoding="utf-8") as f:
                f.write(
                    '{"models": {"light_primary": "gemini-2.5-flash-preview-04-17", '
                    '"pro_primary": "gemini-3.1-flash-lite-preview"}}'
                )

            manager.load_config()

            self.assertEqual(manager.models["light_primary"], "gemini-3.1-flash-lite")
            self.assertEqual(manager.models["pro_primary"], "gemini-3.5-flash")

    def test_build_template_does_not_use_retired_preview_models(self):
        with open("Deploy_Build.ps1", "r", encoding="utf-8-sig") as f:
            script = f.read()

        for retired in RETIRED_OR_UNSAFE_DEFAULTS:
            self.assertNotIn(retired, script)

    def test_model_option_displays_price_but_saves_clean_model_id(self):
        label = format_model_option("gemini-3.1-flash-lite")

        self.assertIn("gemini-3.1-flash-lite", label)
        self.assertIn("$0.25 in", label)
        self.assertIn("$1.50 out", label)
        self.assertEqual(model_id_from_display(label), "gemini-3.1-flash-lite")

    def test_unknown_model_option_still_saves_clean_model_id(self):
        label = format_model_option("gemini-new-model")

        self.assertEqual(label, "gemini-new-model")
        self.assertEqual(model_id_from_display("gemini-new-model — custom note"), "gemini-new-model")

    def test_build_spec_bundles_main_ui_logo(self):
        with open("LighthouseOCR.spec", "r", encoding="utf-8") as f:
            spec = f.read()

        self.assertIn("app_logo.png", spec)

    def test_preview_resolves_image_next_to_pnmh_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pnmh_path = os.path.join(tmp_dir, "PNMH.xlsx")
            image_path = os.path.join(tmp_dir, "invoice.jpg")
            open(pnmh_path, "wb").close()
            open(image_path, "wb").close()

            resolved = _resolve_invoice_image_path(pnmh_path, "invoice.jpg")

            self.assertEqual(os.path.normcase(resolved), os.path.normcase(image_path))

    def test_preview_resolves_image_from_sibling_done_folder(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = os.path.join(tmp_dir, "OUTPUT")
            done_dir = os.path.join(tmp_dir, "DONE")
            os.makedirs(output_dir)
            os.makedirs(done_dir)
            pnmh_path = os.path.join(output_dir, "PNMH.xlsx")
            image_path = os.path.join(done_dir, "invoice.jpg")
            open(pnmh_path, "wb").close()
            open(image_path, "wb").close()

            resolved = _resolve_invoice_image_path(pnmh_path, "invoice.jpg")

            self.assertEqual(os.path.normcase(resolved), os.path.normcase(image_path))


if __name__ == "__main__":
    unittest.main()
