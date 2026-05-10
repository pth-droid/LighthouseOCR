import json
import ast
import random
import time
from google.genai import types
from google.genai.errors import APIError

from core_rate_limiter import global_rate_limiter, EngineCancellationError


def parse_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    try:
        result = ast.literal_eval(text)
        if isinstance(result, dict): return result
    except Exception:
        pass
    raise ValueError(f"Không thể parse JSON từ model.\n\nText:\n{raw_text[:200]}")


def generate_with_fallback(
    client,
    models_to_try: list,
    contents_fn,        # callable(model_name) -> list — builds contents for each call
    data_store,
    rate_bucket_fn,     # callable(model_name) -> str — "flash" or "pro"
    base_wait_fn,       # callable(bucket_key) -> int — base seconds for 429 backoff
    stop_event=None,
    status_callback=None,
):
    """LLM call loop with Primary -> Fallback and 429/503 retry. Returns (raw_text, model_name, usage_metadata)."""
    last_error = None
    for model_cfg in models_to_try:
        model_name = model_cfg["name"]
        model_label = model_cfg["label"]
        bucket_key = rate_bucket_fn(model_name)

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                global_rate_limiter.wait_if_needed(bucket_key, stop_event, status_callback)

                if status_callback and attempt > 0:
                    status_callback(f"🔁 Thử lại lần {attempt} với {model_label}...")

                config = None
                if data_store.should_use_minimal_thinking(model_name, is_primary=model_cfg["is_primary"]):
                    config = types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_budget=0)
                    )

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents_fn(model_name),
                    config=config
                )

                raw = response.text
                if not raw:
                    raise RuntimeError(f"Model {model_label} trả về rỗng.")

                return raw, model_name, getattr(response, "usage_metadata", None)

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
                    base_wait = base_wait_fn(bucket_key)
                    jitter_cap = 5 if bucket_key == "pro" else 3
                    wait = int(base_wait * (2 ** attempt) + random.uniform(0, jitter_cap))
                    if status_callback: status_callback(f"🔁 {model_label} bận (429), đợi {wait}s...")
                    for _ in range(wait, 0, -1):
                        if stop_event and stop_event.is_set():
                            raise EngineCancellationError("STOP_REQUESTED")
                        time.sleep(1)
                else:
                    if status_callback: status_callback(f"⚠️ {model_label} gặp lỗi: {str(e)[:100]}...")
                    break

    raise RuntimeError(f"Tất cả các model đều thất bại. Lỗi cuối cùng: {last_error}")
