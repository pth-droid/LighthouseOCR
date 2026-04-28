import os
import json
import random
import time
import ast
import google.genai as genai
from google.genai import types
from google.genai.errors import APIError

from core_rate_limiter import global_rate_limiter, EngineCancellationError
from data_manager import DataManager

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_FILE = os.path.join(_BASE_DIR, "ocr_text_structurer_skill.md")

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
        raise ValueError(f"Không thể parse JSON từ Flash model.\n\nText:\n{raw_text[:200]}")

    def _generate_with_fallback(self, prompt: str, stop_event=None, status_callback=None) -> tuple[str, dict]:
        """Thực hiện gọi LLM với cơ chế Primary -> Fallback."""
        model_primary = self.data_store.models.get("light_primary")
        model_fallback = self.data_store.models.get("light_fallback")

        models_to_try = [
            {"name": model_primary, "label": "Flash 3.1 Lite", "is_primary": True},
            {"name": model_fallback, "label": "Flash 2.5 Fallback", "is_primary": False}
        ]
        
        last_error = None
        for model_cfg in models_to_try:
            model_name = model_cfg["name"]
            model_label = model_cfg["label"]
            
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    global_rate_limiter.wait_if_needed("flash", stop_event, status_callback)
                    
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
                        contents=[prompt],
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
                        break # Chuyển sang fallback ngay

                    is_rate_limit = isinstance(e, APIError) and getattr(e, 'code', None) in (429, 503)
                    if (is_rate_limit or "429" in error_msg or "503" in error_msg) and attempt < max_retries:
                        wait = int(10 * (2 ** attempt) + random.uniform(0, 3))
                        if status_callback: status_callback(f"🔁 {model_label} bận (429), đợi {wait}s...")
                        for _ in range(wait, 0, -1):
                            if stop_event and stop_event.is_set():
                                raise EngineCancellationError("STOP_REQUESTED")
                            time.sleep(1)
                    else:
                        if status_callback: status_callback(f"⚠️ {model_label} gặp lỗi: {str(e)[:100]}...")
                        break
        
        raise RuntimeError(f"Tất cả các model Flash đều thất bại. Lỗi cuối cùng: {last_error}")

    def structure_text_to_json(self, raw_paddle_text: str, avg_confidence: float, stop_event=None, status_callback=None) -> dict:
        if status_callback:
            status_callback("🚀 Gửi dữ liệu thô đẩy lên hạ tầng LLM Flash 3.1 cấu trúc thành JSON...")
            
        combined_prompt = f"{self.prompt_template}\n\nRAW_TEXT_INPUT_FROM_PADDLEOCR:\n{raw_paddle_text}"
        
        raw_text, usage = self._generate_with_fallback(combined_prompt, stop_event, status_callback)
        
        result = self._parse_json_response(raw_text)
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
