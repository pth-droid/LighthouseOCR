import json
import os
import tempfile
import unittest

from data_manager import DataManager


class StructurePipelineConfigTests(unittest.TestCase):
    def test_default_pipeline_mode_is_structure_default(self):
        manager = DataManager()
        self.assertEqual(manager.ocr_pipeline_mode, "structure_default")

    def test_load_config_accepts_legacy_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = DataManager()
            manager.config_file = os.path.join(tmp_dir, "lighthouse_config.json")
            with open(manager.config_file, "w", encoding="utf-8") as f:
                json.dump({"ocr_pipeline_mode": "legacy_hybrid"}, f)

            manager.load_config()

            self.assertEqual(manager.ocr_pipeline_mode, "legacy_hybrid")

    def test_unknown_pipeline_mode_falls_back_to_structure_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = DataManager()
            manager.config_file = os.path.join(tmp_dir, "lighthouse_config.json")
            with open(manager.config_file, "w", encoding="utf-8") as f:
                json.dump({"ocr_pipeline_mode": "unknown"}, f)

            manager.load_config()

            self.assertEqual(manager.ocr_pipeline_mode, "structure_default")


if __name__ == "__main__":
    unittest.main()
