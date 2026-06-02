import sys
import os
import json
import logging
import warnings

# Optimize paddle startup and avoid network check for models if cached
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ.pop("FLAGS_selected_gpus", None)  # must not be empty string — paddle does int(value[0])
warnings.filterwarnings('ignore')
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddleocr").setLevel(logging.ERROR)
DEFAULT_OCR_RUNTIME_MODE = "stable"


def _parse_major_version(version_text: str) -> int:
    try:
        return int(str(version_text).split(".", 1)[0])
    except Exception:
        return 0


def _normalize_ocr_runtime_mode(runtime_mode) -> str:
    aliases = {
        "": DEFAULT_OCR_RUNTIME_MODE,
        "stable": "stable",
        "cpu": "stable",
        "safe": "stable",
        "cpu_fast": "cpu_fast",
        "fast": "cpu_fast",
        "gpu": "gpu",
        "cuda": "gpu",
    }
    return aliases.get(str(runtime_mode or "").strip().lower(), DEFAULT_OCR_RUNTIME_MODE)


def _load_ocr_runtime_mode() -> str:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "env", "lighthouse_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return _normalize_ocr_runtime_mode(cfg.get("ocr_mode"))
        except Exception:
            pass
    return DEFAULT_OCR_RUNTIME_MODE


def _build_ocr_engine(runtime_mode=None):
    import paddleocr
    from paddleocr import PaddleOCR

    version_str = getattr(paddleocr, "__version__", "0")
    major = _parse_major_version(version_str)
    runtime_mode = _normalize_ocr_runtime_mode(runtime_mode)
    if major >= 3:
        # PaddleOCR 3.x (PP-OCRv5): let lang="vi" auto-select models.
        # Explicit model names are omitted — they changed between 3.0 and 3.5
        # and auto-selection is the stable API across minor versions.
        ocr = PaddleOCR(
            lang="vi",
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="gpu" if runtime_mode == "gpu" else "cpu",
            enable_mkldnn=(runtime_mode == "cpu_fast"),
        )
        print(f"[OCR] PaddleOCR {version_str} (PP-OCRv5, mode={runtime_mode}, lang=vi)")
        return ocr, "v3"

    ocr = PaddleOCR(
        lang="vi",
        ocr_version="PP-OCRv4",
        show_log=False,
        use_gpu=False,
        use_angle_cls=True,
    )
    return ocr, "legacy"


def _run_v3_ocr_with_fallback(image_path, requested_mode):
    requested_mode = _normalize_ocr_runtime_mode(requested_mode)
    modes_to_try = [requested_mode]
    if requested_mode != DEFAULT_OCR_RUNTIME_MODE:
        modes_to_try.append(DEFAULT_OCR_RUNTIME_MODE)

    last_error = None
    for index, runtime_mode in enumerate(modes_to_try):
        try:
            ocr, _ = _build_ocr_engine(runtime_mode)
            result = ocr.predict(image_path)
            if index > 0:
                print(f"[OCR] Requested mode '{requested_mode}' failed. Fell back to stable CPU.")
            return result
        except Exception as exc:
            last_error = exc
            if index == len(modes_to_try) - 1:
                raise
            print(f"[OCR] Mode '{runtime_mode}' failed: {exc}. Retrying with stable CPU...", file=sys.stderr)

    raise last_error or RuntimeError("OCR runtime mode fallback failed.")


def _create_v3_engine_with_fallback(requested_mode):
    requested_mode = _normalize_ocr_runtime_mode(requested_mode)
    modes_to_try = [requested_mode]
    if requested_mode != DEFAULT_OCR_RUNTIME_MODE:
        modes_to_try.append(DEFAULT_OCR_RUNTIME_MODE)

    last_error = None
    for index, runtime_mode in enumerate(modes_to_try):
        try:
            ocr, engine_mode = _build_ocr_engine(runtime_mode)
            if index > 0:
                print(f"[OCR] Requested mode '{requested_mode}' failed during startup. Fell back to stable CPU.")
            return ocr, engine_mode
        except Exception as exc:
            last_error = exc
            if index == len(modes_to_try) - 1:
                raise
            print(f"[OCR] Mode '{runtime_mode}' failed during startup: {exc}. Retrying with stable CPU...", file=sys.stderr)

    raise last_error or RuntimeError("OCR runtime mode startup fallback failed.")


def _collect_from_legacy_result(result):
    output_data = {"texts": [], "scores": []}
    if not result:
        return output_data

    for page_res in result:
        if not page_res:
            continue
        for line_res in page_res:
            if not isinstance(line_res, (list, tuple)) or len(line_res) < 2:
                continue
            rec_pair = line_res[1]
            if not isinstance(rec_pair, (list, tuple)) or len(rec_pair) < 2:
                continue
            text, score = rec_pair[0], rec_pair[1]
            if text and str(text).strip():
                output_data["texts"].append(str(text).strip())
                output_data["scores"].append(float(score))
    return output_data


def _collect_from_v3_result(result):
    output_data = {"texts": [], "scores": []}
    if not result:
        return output_data

    for page_res in result:
        payload = getattr(page_res, "json", None)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict):
            continue

        texts = payload.get("rec_texts")
        scores = payload.get("rec_scores")
        if texts is None or scores is None:
            nested = payload.get("res", {})
            if isinstance(nested, dict):
                texts = nested.get("rec_texts")
                scores = nested.get("rec_scores")

        if not isinstance(texts, list) or not isinstance(scores, list):
            print(f"WARNING: PaddleOCR v3 result object has unexpected schema. Skipping page. Keys: {list(payload.keys())}")
            continue

        for text, score in zip(texts, scores):
            if text and str(text).strip():
                output_data["texts"].append(str(text).strip())
                output_data["scores"].append(float(score))
    return output_data

def run_ocr(image_path, output_path):
    try:
        requested_runtime_mode = _load_ocr_runtime_mode()
        import paddleocr
        major = _parse_major_version(getattr(paddleocr, "__version__", "0"))
        
        # Warmup mode
        if image_path == "--warmup":
            if major >= 3:
                _create_v3_engine_with_fallback(requested_runtime_mode)
            else:
                _build_ocr_engine(requested_runtime_mode)
            print("Warmup successful. Models are downloaded and ready.")
            sys.exit(0)
            
        if major >= 3:
            result = _run_v3_ocr_with_fallback(image_path, requested_runtime_mode)
            output_data = _collect_from_v3_result(result)
        else:
            ocr, _ = _build_ocr_engine(requested_runtime_mode)
            result = ocr.ocr(image_path, cls=True)
            output_data = _collect_from_legacy_result(result)
                        
        # Write output as JSON
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False)
            
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"ERROR: {str(e)}", file=sys.stderr)
        traceback.print_exc()  # already goes to stderr by default
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--warmup":
        run_ocr("--warmup", None)
    elif len(sys.argv) == 3:
        run_ocr(sys.argv[1], sys.argv[2])
    else:
        print("Usage: ocr_runner.py <image_path> <output_json_path> OR ocr_runner.py --warmup")
        sys.exit(1)
