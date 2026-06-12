import io
import json
import os
import tempfile
import unittest
from unittest import mock

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

    def test_runner_disables_bytecode_cache_for_portable_env(self):
        self.assertTrue(ocr_structure_runner.sys.dont_write_bytecode)

    def test_worker_reuses_pipeline_for_multiple_jobs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_one = os.path.join(tmp_dir, "one.json")
            output_two = os.path.join(tmp_dir, "two.json")
            input_stream = io.StringIO(
                json.dumps({"job_id": "1", "image_path": "one.jpg", "output_path": output_one}) + "\n" +
                json.dumps({"job_id": "2", "image_path": "two.jpg", "output_path": output_two}) + "\n"
            )
            output_stream = io.StringIO()
            pipeline = object()

            def fake_predict(active_pipeline, image_path):
                self.assertIs(active_pipeline, pipeline)
                return {
                    "engine": "PPStructureV3",
                    "pages": [],
                    "raw_text": image_path,
                    "avg_confidence": 0.9,
                    "elapsed_seconds": 0.1,
                }

            with mock.patch.object(ocr_structure_runner, "_create_pipeline", return_value=pipeline) as create_pipeline:
                with mock.patch.object(ocr_structure_runner, "_predict_structure", side_effect=fake_predict):
                    exit_code = ocr_structure_runner.run_worker(input_stream, output_stream)

            self.assertEqual(exit_code, 0)
            self.assertEqual(create_pipeline.call_count, 1)
            responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
            self.assertEqual([response["ok"] for response in responses], [True, True])
            with open(output_one, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["raw_text"], "one.jpg")
            with open(output_two, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["raw_text"], "two.jpg")

    def test_worker_reports_job_error_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "ok.json")
            input_stream = io.StringIO(
                json.dumps({"job_id": "bad", "image_path": "bad.jpg", "output_path": os.path.join(tmp_dir, "bad.json")}) + "\n" +
                json.dumps({"job_id": "ok", "image_path": "ok.jpg", "output_path": output_path}) + "\n"
            )
            output_stream = io.StringIO()

            def fake_predict(_pipeline, image_path):
                if image_path == "bad.jpg":
                    raise RuntimeError("bad invoice")
                return {
                    "engine": "PPStructureV3",
                    "pages": [],
                    "raw_text": "ok",
                    "avg_confidence": 0.8,
                    "elapsed_seconds": 0.2,
                }

            with mock.patch.object(ocr_structure_runner, "_create_pipeline", return_value=object()):
                with mock.patch.object(ocr_structure_runner, "_predict_structure", side_effect=fake_predict):
                    exit_code = ocr_structure_runner.run_worker(input_stream, output_stream)

            self.assertEqual(exit_code, 0)
            responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
            self.assertEqual(responses[0]["ok"], False)
            self.assertIn("bad invoice", responses[0]["error"])
            self.assertEqual(responses[1]["ok"], True)
            self.assertTrue(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
