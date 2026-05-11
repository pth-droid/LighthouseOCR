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


def _parse_major_version(version_text: str) -> int:
    try:
        return int(str(version_text).split(".", 1)[0])
    except Exception:
        return 0


def _build_ocr_engine():
    import paddleocr
    from paddleocr import PaddleOCR

    major = _parse_major_version(getattr(paddleocr, "__version__", "0"))
    if major >= 3:
        # PaddleOCR 3.x introduces PP-OCRv5 and a new Result-object API.
        ocr = PaddleOCR(
            lang="vi",
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
        )
        return ocr, "v3"

    ocr = PaddleOCR(
        lang="vi",
        ocr_version="PP-OCRv4",
        show_log=False,
        use_gpu=False,
        use_angle_cls=True,
    )
    return ocr, "legacy"


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
        ocr, engine_mode = _build_ocr_engine()
        
        # Warmup mode
        if image_path == "--warmup":
            print("Warmup successful. Models are downloaded and ready.")
            sys.exit(0)
            
        if engine_mode == "v3":
            result = ocr.predict(image_path)
            output_data = _collect_from_v3_result(result)
        else:
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
