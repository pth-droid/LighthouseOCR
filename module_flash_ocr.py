import os
import json
import random
import time
import ast
import google.genai as genai
from google.genai import types
from google.genai.errors import APIError

from core_rate_limiter import global_rate_limiter, EngineCancellationError
from core_llm_client import parse_json_response, generate_with_fallback
from data_manager import DataManager
from path_utils import get_asset_path

_SKILL_FILE = get_asset_path("ocr_text_structurer_skill.md")

class FlashTextStructurer:
    def __init__(self, api_key: str, data_store: DataManager):
        self.api_key = api_key
        self.data_store = data_store
        self.client = genai.Client(api_key=self.api_key)
        self.prompt_template = ""
        
        try:
            with open(_SKILL_FILE, "r", encoding="utf-8") as f:
                skill_content = f.read()
            
            # INJECT Context cực mạnh cho Text Structuring
            injection = f"""
---
## INJECTED DICTIONARY (DO NOT IGNORE)

### Danh sách Nhà Cung Cấp (Mã=Tên đầy đủ, dùng để map alias):
{data_store.suppliers_context_str}

### Danh sách Vật Tư / Nguyên Liệu (Tên / Đơn vị tính):
{data_store.items_context_str}

### Location Abbreviations:
- "12 D.D.N" / "12 ddn" → "12 Dương Đình Nghệ, An Hải, Đà Nẵng"
---
"""
            self.prompt_template = injection + skill_content
            
        except Exception as e:
            raise RuntimeError(f"Engine failed to build Flash Text Prompts: {e}")

    def structure_text_to_json(self, raw_paddle_text: str, avg_confidence: float, stop_event=None, status_callback=None) -> dict:
        if status_callback:
            status_callback("🚀 Gửi dữ liệu thô đẩy lên hạ tầng LLM Flash 3.1 cấu trúc thành JSON...")
            
        combined_prompt = f"{self.prompt_template}\n\nRAW_TEXT_INPUT_FROM_PADDLEOCR:\n{raw_paddle_text}"

        models_to_try = [
            {"name": self.data_store.models.get("light_primary"), "label": "Flash 3.1 Lite", "is_primary": True},
            {"name": self.data_store.models.get("light_fallback"), "label": "Flash 2.5 Fallback", "is_primary": False}
        ]
        raw_text, model_name, usage_meta = generate_with_fallback(
            self.client, models_to_try,
            contents_fn=lambda _: [combined_prompt],
            data_store=self.data_store,
            rate_bucket_fn=lambda _: "flash",
            base_wait_fn=lambda _: 10,
            stop_event=stop_event,
            status_callback=status_callback,
        )
        usage = {
            "model": model_name,
            "prompt_tokens": getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0,
            "response_tokens": getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0,
            "total_tokens": getattr(usage_meta, "total_token_count", 0) if usage_meta else 0,
        }

        result = parse_json_response(raw_text)
        result["_telemetry"] = usage
        
        # Bơm lại điểm số confidence của Paddle vào JSON
        if "document_info" not in result:
            result["document_info"] = {}
        result["document_info"]["confidence_score"] = float(round(avg_confidence, 3))
        
        return result

_flash_instance = None
_flash_data_version = None
def get_flash_structurer(api_key: str, data_store: DataManager):
    global _flash_instance, _flash_data_version
    if not _flash_instance or _flash_instance.api_key != api_key or _flash_data_version != data_store._data_version:
        _flash_instance = FlashTextStructurer(api_key, data_store)
        _flash_data_version = data_store._data_version
    return _flash_instance
