import unittest

from ocr_pipeline_structure import _should_keep_processing


class OcrPipelineStructureTests(unittest.TestCase):
    def test_should_keep_processing_stops_on_event(self):
        class StopEvent:
            def is_set(self):
                return True

        self.assertFalse(_should_keep_processing(StopEvent()))

    def test_should_keep_processing_continues_when_not_stopped(self):
        class StopEvent:
            def is_set(self):
                return False

        self.assertTrue(_should_keep_processing(StopEvent()))


if __name__ == "__main__":
    unittest.main()
