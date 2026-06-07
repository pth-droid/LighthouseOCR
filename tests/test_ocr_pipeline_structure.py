import unittest

from ocr_pipeline_structure import (
    _has_reviewable_invoice_data,
    _should_keep_processing,
    _should_use_direct_vision_fallback,
    _should_use_vision_after_light_fallback,
)


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

    def test_low_confidence_missing_items_routes_directly_to_vision(self):
        validation = {
            "can_use_local_result": False,
            "missing_required_fields": ["items", "total_amount"],
            "confidence": 0.407,
        }

        self.assertTrue(_should_use_direct_vision_fallback(validation))

    def test_light_fallback_empty_result_routes_to_vision(self):
        validation = {
            "can_use_local_result": False,
            "missing_required_fields": ["items"],
            "confidence": 0.407,
        }

        self.assertTrue(_should_use_vision_after_light_fallback(validation))

    def test_supplier_only_missing_does_not_force_vision(self):
        validation = {
            "can_use_local_result": False,
            "missing_required_fields": ["supplier_name_code"],
            "confidence": 0.407,
        }

        self.assertFalse(_should_use_direct_vision_fallback(validation))
        self.assertFalse(_should_use_vision_after_light_fallback(validation))

    def test_empty_items_are_not_reviewable(self):
        self.assertFalse(_has_reviewable_invoice_data({"items": []}))
        self.assertFalse(_has_reviewable_invoice_data({}))
        self.assertTrue(_has_reviewable_invoice_data({"items": [{"product_name": "Bo"}]}))


if __name__ == "__main__":
    unittest.main()
