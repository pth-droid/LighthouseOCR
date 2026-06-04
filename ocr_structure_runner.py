import json
import logging
import os
import sys
import tempfile
import time
import warnings

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ.pop("FLAGS_selected_gpus", None)
warnings.filterwarnings("ignore")
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddleocr").setLevel(logging.ERROR)

_OMITTED_PAYLOAD_KEYS = {
    "input_img",
    "output_img",
    "doc_preprocessed_img",
    "image",
    "img",
    "ori_img",
    "rot_img",
    "vis_img",
}


def _make_safe_json(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        safe = {}
        for k, v in value.items():
            key = str(k)
            if key.lower() in _OMITTED_PAYLOAD_KEYS:
                continue
            safe[key] = _make_safe_json(v)
        return safe
    if isinstance(value, (list, tuple)):
        return [_make_safe_json(v) for v in value]
    if hasattr(value, "tolist"):
        try:
            return _make_safe_json(value.tolist())
        except Exception:
            return str(value)
    return str(value)


def _extract_text_and_scores(page_payload):
    texts = []
    scores = []
    candidates = [page_payload]
    if isinstance(page_payload, dict):
        candidates.extend([
            page_payload.get("res", {}),
            page_payload.get("overall_ocr_res", {}),
        ])

    for payload in candidates:
        if not isinstance(payload, dict):
            continue
        rec_texts = payload.get("rec_texts") or payload.get("texts") or []
        rec_scores = payload.get("rec_scores") or payload.get("scores") or []
        if isinstance(rec_texts, list):
            texts.extend(str(x).strip() for x in rec_texts if str(x).strip())
        if isinstance(rec_scores, list):
            for score in rec_scores:
                try:
                    scores.append(float(score))
                except (TypeError, ValueError):
                    pass
    return texts, scores


def _build_output(result, elapsed_seconds):
    pages = []
    all_texts = []
    all_scores = []
    for page in result or []:
        payload = page.json() if hasattr(page, "json") and callable(page.json) else page
        safe_payload = _make_safe_json(payload)
        texts, scores = _extract_text_and_scores(safe_payload if isinstance(safe_payload, dict) else {})
        all_texts.extend(texts)
        all_scores.extend(scores)
        pages.append(safe_payload)

    avg_confidence = sum(all_scores) / len(all_scores) if all_scores else 0.0
    return {
        "engine": "PPStructureV3",
        "pages": pages,
        "raw_text": "\n".join(all_texts),
        "texts": all_texts,
        "scores": all_scores,
        "avg_confidence": avg_confidence,
        "elapsed_seconds": elapsed_seconds,
    }


def _format_runtime_error(exc):
    message = str(exc)
    lower = message.lower()
    if "pp-structurev3" in lower and "additional dependencies" in lower:
        return (
            f"{message}\n"
            "PP-StructureV3 is installed, but PaddleX OCR extras are missing. "
            "Run Setup_Moi_Truong.bat again, or run this command inside the app folder: "
            'env\\python.exe -m pip install "paddlex[ocr]==3.6.1"'
        )
    return message


def run_structure(image_path, output_path):
    try:
        from paddleocr import PPStructureV3

        started_at = time.perf_counter()
        pipeline = PPStructureV3(
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_table_recognition=True,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_seal_recognition=False,
        )
        result = pipeline.predict(image_path, visualize=False)
        output = _build_output(result, time.perf_counter() - started_at)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False)
        return 0
    except Exception as exc:
        import traceback

        print(f"ERROR: {_format_runtime_error(exc)}", file=sys.stderr)
        traceback.print_exc()
        return 1


def run_check():
    try:
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = os.path.join(tmp_dir, "pp_structure_check.png")
            output_path = os.path.join(tmp_dir, "pp_structure_check.json")
            image = np.full((256, 256, 3), 255, dtype=np.uint8)
            cv2.putText(
                image,
                "Lighthouse OCR",
                (18, 132),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )
            if not cv2.imwrite(image_path, image):
                raise RuntimeError("Could not create PP-StructureV3 check image.")
            exit_code = run_structure(image_path, output_path)
            if exit_code != 0:
                return exit_code
            if not os.path.exists(output_path):
                print("ERROR: PP-StructureV3 check did not create output JSON.", file=sys.stderr)
                return 1
        print("PP-StructureV3 check successful.")
        return 0
    except Exception as exc:
        import traceback

        print(f"ERROR: {_format_runtime_error(exc)}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        sys.exit(run_check())
    if len(sys.argv) != 3:
        print("Usage: ocr_structure_runner.py <image_path> <output_json_path> OR ocr_structure_runner.py --check", file=sys.stderr)
        sys.exit(1)
    sys.exit(run_structure(sys.argv[1], sys.argv[2]))
