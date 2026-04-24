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
from data_manager import DataManager

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_FILE = os.path.join(_BASE_DIR, "ocr_vision_handwritten_skill.md")

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

    def _parse_json_response(self, raw_text: str) -> dict:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            result = ast.literal_eval(text)
            if isinstance(result, dict): return result
        except Exception:
            pass
        raise ValueError(f"Không thể parse JSON từ Pro model.\n\nText:\n{raw_text[:200]}")

    def _generate_with_fallback(self, image: Image.Image, stop_event=None, status_callback=None) -> tuple[str, dict]:
        """Thực hiện gọi LLM Vision với cơ chế Primary -> Fallback."""
        model_primary = self.data_store.models.get("pro_primary")
        model_fallback = self.data_store.models.get("pro_fallback")

        models_to_try = [
            {"name": model_primary, "label": "Flash 3.1 (Vision)", "is_primary": True},
            {"name": model_fallback, "label": "Pro 2.5 (Vision Fallback)", "is_primary": False}
        ]
        
        last_error = None
        for model_cfg in models_to_try:
            model_name = model_cfg["name"]
            model_label = model_cfg["label"]
            
            # Rate limit key: dùng "pro" cho 2.5-pro, "flash" cho 3.1-flash
            rate_limit_key = "pro" if "pro" in model_name.lower() else "flash"
            
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    global_rate_limiter.wait_if_needed(rate_limit_key, stop_event, status_callback)
                    
                    if status_callback and attempt > 0:
                        status_callback(f"🔁 Thử lại lần {attempt} với {model_label}...")

                    # Chế độ thinking_mode='minimal' chỉ cho Primary model đời mới
                    config = None
                    if self.data_store.should_use_minimal_thinking(model_name, is_primary=model_cfg["is_primary"]):
                        config = types.GenerateContentConfig(
                            thinking_config=types.ThinkingConfig(thinking_budget=0)
                        )

                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[self.prompt_template, image],
                        config=config
                    )
                    
                    usage = {
                        "model": model_name,
                        "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else 0,
                        "response_tokens": getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else 0,
                        "total_tokens": getattr(response.usage_metadata, "total_token_count", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else 0,
                    }
                    
                    raw = response.text
                    if not raw:
                        raise RuntimeError(f"Model {model_label} trả về rỗng.")
                    
                    return raw, usage
                    
                except EngineCancellationError:
                    raise
                except Exception as e:
                    last_error = e
                    error_msg = str(e).upper()
                    if "404" in error_msg or "NOT_FOUND" in error_msg:
                        if status_callback: status_callback(f"⚠️ Model '{model_name}' không tồn tại (404).")
                        break

                    is_rate_limit = isinstance(e, APIError) and getattr(e, 'code', None) in (429, 503)
                    if (is_rate_limit or "429" in error_msg or "503" in error_msg) and attempt < max_retries:
                        # Delay cho Pro cần dài hơn Flash
                        base_wait = 35 if rate_limit_key == "pro" else 15
                        wait = int(base_wait * (2 ** attempt) + random.uniform(0, 5)) 
                        if status_callback: status_callback(f"🔁 {model_label} bận (429), đợi {wait}s...")
                        for _ in range(wait, 0, -1):
                            if stop_event and stop_event.is_set():
                                raise EngineCancellationError("STOP_REQUESTED")
                            time.sleep(1)
                    else:
                        if status_callback: status_callback(f"⚠️ {model_label} gặp lỗi: {str(e)[:100]}...")
                        break
        
        raise RuntimeError(f"Tất cả các model Vision đều thất bại. Lỗi cuối cùng: {last_error}")

    def extract_image_directly(self, image: Image.Image, stop_event=None, status_callback=None) -> dict:
        if status_callback:
            status_callback("🧠 Nét mờ/Tay: Kích hoạt LLM Flash 3.1 Vision càn quét bức ảnh...")
            
        raw_text, usage = self._generate_with_fallback(image, stop_event, status_callback)
        
        result = self._parse_json_response(raw_text)
        result["_telemetry"] = usage
        
        if "document_info" not in result:
            result["document_info"] = {}
        result["document_info"]["confidence_score"] = "PRO_FALLBACK_HANDLED"
        
        return result

_pro_instance = None
def get_pro_ocr(api_key: str, data_store: DataManager):
    global _pro_instance
    if not _pro_instance or _pro_instance.api_key != api_key:
        _pro_instance = ProVisionOCR(api_key, data_store)
    return _pro_instance
