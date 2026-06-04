import os
import json
import random
import time
import ast
from PIL import Image
import google.genai as genai
from google.genai import types
from google.genai.errors import APIError

from core_rate_limiter import global_rate_limiter, EngineCancellationError
from core_llm_client import parse_json_response, generate_with_fallback
from data_manager import DataManager
from path_utils import get_asset_path

_SKILL_FILE = get_asset_path("ocr_vision_handwritten_skill.md")

class ProVisionOCR:
    def __init__(self, api_key: str, data_store: DataManager):
        self.api_key = api_key
        self.data_store = data_store
        self.client = genai.Client(api_key=self.api_key)
        self.prompt_template = ""
        
        try:
            with open(_SKILL_FILE, "r", encoding="utf-8") as f:
                skill_content = f.read()
            
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
            raise RuntimeError(f"Engine failed to build Pro Vision Prompts: {e}")

    def extract_image_directly(self, image: Image.Image, stop_event=None, status_callback=None) -> dict:
        if status_callback:
            status_callback("🧠 Nét mờ/Tay: Kích hoạt LLM Flash 3.1 Vision càn quét bức ảnh...")
            
        models_to_try = [
            {"name": self.data_store.models.get("pro_primary"), "label": "Gemini 3.5 Flash Vision", "is_primary": True},
            {"name": self.data_store.models.get("pro_fallback"), "label": "Gemini 3.1 Pro Preview Vision Fallback", "is_primary": False}
        ]
        raw_text, model_name, usage_meta = generate_with_fallback(
            self.client, models_to_try,
            contents_fn=lambda _: [self.prompt_template, image],
            data_store=self.data_store,
            rate_bucket_fn=lambda name: "pro" if "pro" in name.lower() else "flash",
            base_wait_fn=lambda bk: 35 if bk == "pro" else 15,
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
        
        if "document_info" not in result:
            result["document_info"] = {}
        result["document_info"]["confidence_score"] = "PRO_FALLBACK_HANDLED"
        
        return result

_pro_instance = None
_pro_data_version = None
def get_pro_ocr(api_key: str, data_store: DataManager):
    global _pro_instance, _pro_data_version
    if not _pro_instance or _pro_instance.api_key != api_key or _pro_data_version != data_store._data_version:
        _pro_instance = ProVisionOCR(api_key, data_store)
        _pro_data_version = data_store._data_version
    return _pro_instance
