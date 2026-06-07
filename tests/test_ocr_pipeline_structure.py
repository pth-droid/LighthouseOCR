import unittest

from ocr_pipeline_structure import (
    _has_reviewable_invoice_data,
    _json_misses_detected_item_rows,
    _should_keep_processing,
    _should_use_direct_vision_fallback,
    _should_use_vision_after_light_fallback,
    _supplier_looks_suspicious_after_light_fallback,
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

    def test_salesperson_line_is_suspicious_supplier_after_light_fallback(self):
        invoice = {
            "supplier_info": {
                "supplier_name_code": "HRUOU",
                "supplier_name_raw": "Hin HRC DN",
            }
        }
        validation_before = {"missing_required_fields": ["supplier_name_code"]}

        self.assertTrue(_supplier_looks_suspicious_after_light_fallback(invoice, validation_before))

    def test_company_raw_supplier_is_not_suspicious(self):
        invoice = {
            "supplier_info": {
                "supplier_name_code": "LSON",
                "supplier_name_raw": "CONG TY TNHH SAN XUAT THUONG MAI DICH VU LAT SON",
            }
        }
        validation_before = {"missing_required_fields": ["item_pricing"]}

        self.assertFalse(_supplier_looks_suspicious_after_light_fallback(invoice, validation_before))

    def test_detects_when_json_has_fewer_items_than_numbered_table_rows(self):
        normalized = {
            "raw_text": "\n".join([
                "STT",
                "Ma hang",
                "Ten hang",
                "1",
                "NL9 - TONIC",
                "Tonic",
                "2",
                "DLM SCA KD 500GR",
                "Sua chua an KD 500g",
                "3",
                "STND",
                "Sinh to nha dam",
                "Cong tien hang",
            ])
        }
        invoice = {"items": [{"product_name": "Tonic"}, {"product_name": "Sinh to nha dam"}]}

        self.assertTrue(_json_misses_detected_item_rows(invoice, normalized))


if __name__ == "__main__":
    unittest.main()
