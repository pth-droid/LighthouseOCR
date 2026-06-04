# Advanced PP-Structure Default Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a completely separate PaddleOCR 3.6.0 / PP-StructureV3 invoice pipeline and make it the default app path: `INPUT -> new pipeline -> fallback light model -> existing calculator/export`.

**Architecture:** Do not edit the existing `module_paddle_ocr.py` or `ocr_runner.py`. Add a new PP-Structure runner, a new invoice extraction pipeline, and a new business-KIE layer that uses the master data in `Data structure/`. The old Paddle/Gemini pipeline remains available as a selectable legacy mode, but the default config becomes the new PP-Structure pipeline.

**Tech Stack:** Python 3.10, PyQt5, PaddleOCR 3.6.0, PP-StructureV3, PP-OCRv5, OpenCV, Pillow, openpyxl, existing Gemini Flash light fallback, existing `DataManager`, existing `module_calculator.py`, existing `core_excel_mapper.py`.

---

## Decisions Locked In

- Do not touch `module_paddle_ocr.py`.
- Do not touch `ocr_runner.py`.
- Create separate new files for the PP-Structure pipeline.
- Set the new pipeline as the default mode for the app.
- Normal app runs must not write PP-Structure debug images, Markdown, DOCX, or large per-invoice artifact folders.
- Use the light model only as a fallback when local extraction is weak or incomplete.
- Do not compare against the old OCR model as a replacement gate.
- The final JSON shape must remain compatible with downstream code:

```json
{
  "document_info": {},
  "supplier_info": {},
  "transaction_info": {},
  "items": [],
  "totals": {}
}
```

## Why KIE Is Now Stronger Than A Generic LayoutLM/SER Start

The project already has business data that can power a practical KIE layer without first training SER/RE:

- `Data structure/Danh sach nha cung cap.xlsx`: supplier code, supplier name, and common purchased products.
- `Data structure/Danh mục vật tư, hàng hoá.xlsx`: item code, item name, unit, conversion unit, conversion factor, reference purchase price, and department/group hints.
- `Data structure/Danh sach kho.xlsx`: department to warehouse code mapping.
- `Data structure/Tu_dien_alias.csv`: known OCR alias to item code plus loose unit and conversion factor.
- `Data structure/OCR_Difficult_Reports.csv`: known hard cases and correction reasons.

This is enough for a strong first KIE layer:

```text
PP-StructureV3 visual/layout/table output
-> candidate fields
-> supplier/item/unit/date/total matching against DataManager
-> validation and confidence
-> final JSON
```

LayoutLM/SER/RE can still be useful later, but they need bounding-box/entity labels to be reliable. The current data folder is better used first as a business knowledge base: like a clerk with the company catalog, supplier list, alias list, and past mistake notes beside them.

## New Default Data Flow

```text
INPUT folder
-> image_processor.prepare_image
-> module_paddle_structure_ocr.StructurePaddleOCREngine
-> ocr_structure_runner.py subprocess
-> PPStructureV3 predict(visualize=False, table=True, formula/chart/seal off)
-> structure_result_normalizer.py
-> business_kie.py using DataManager and Data structure files
-> invoice_json_builder.py
-> supplier_enrichment.py local-first NCC resolver with confidence/evidence
-> invoice_validation.py
-> if weak: fallback_light_structurer.py
-> supplier_enrichment.py rerun after fallback JSON
-> module_calculator.py
-> core_excel_mapper.py
-> review UI
```

## File Structure

- Create `ocr_structure_runner.py`: isolated subprocess script for PP-StructureV3. It must not import or reuse `ocr_runner.py`.
- Create `module_paddle_structure_ocr.py`: app-side wrapper that calls `ocr_structure_runner.py`. It must not import or subclass `LocalPaddleOCREngine`.
- Create `structure_result_normalizer.py`: converts PP-StructureV3 result objects into stable internal dictionaries.
- Create `business_kie.py`: extracts supplier, invoice fields, items, units, departments, and totals using local master data.
- Create `supplier_enrichment.py`: resolves missing NCC before calculator using local supplier sample products, with false-positive guards and `_supplier_resolution` metadata.
- Create `invoice_validation.py`: scores whether local extraction is strong enough or should fall back to the light model.
- Create `invoice_json_builder.py`: maps local candidates into the app's existing final JSON schema.
- Create `fallback_light_structurer.py`: calls the existing light model with normalized PP-Structure text/table context only when local validation is weak.
- Create `ocr_pipeline_structure.py`: separate full pipeline for image folder processing.
- Modify `data_manager.py`: add default `ocr_pipeline_mode = "structure_default"`.
- Modify `admin_dialogs.py` and `main_app_qt.py`: show pipeline mode in settings and default to the new pipeline.
- Modify `main_app_qt.py`: start the new pipeline by default. Keep legacy mode selectable.
- Modify `Setup_Moi_Truong.bat` and `Setup_Nguon.bat`: ensure PaddleOCR 3.6.0 is installed with the document parsing dependencies needed by PP-StructureV3.
- Modify `LighthouseOCR.spec` if new runner/modules are not automatically bundled.

---

### Task 1: Config Default Becomes New PP-Structure Pipeline

**Files:**
- Modify: `data_manager.py`
- Test: `tests/test_structure_pipeline_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_structure_pipeline_config.py`:

```python
import json
import os
import tempfile
import unittest

from data_manager import DataManager


class StructurePipelineConfigTests(unittest.TestCase):
    def test_default_pipeline_mode_is_structure_default(self):
        manager = DataManager()
        self.assertEqual(manager.ocr_pipeline_mode, "structure_default")

    def test_load_config_accepts_legacy_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = DataManager()
            manager.config_file = os.path.join(tmp_dir, "lighthouse_config.json")
            with open(manager.config_file, "w", encoding="utf-8") as f:
                json.dump({"ocr_pipeline_mode": "legacy_hybrid"}, f)

            manager.load_config()

            self.assertEqual(manager.ocr_pipeline_mode, "legacy_hybrid")

    def test_unknown_pipeline_mode_falls_back_to_structure_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = DataManager()
            manager.config_file = os.path.join(tmp_dir, "lighthouse_config.json")
            with open(manager.config_file, "w", encoding="utf-8") as f:
                json.dump({"ocr_pipeline_mode": "unknown"}, f)

            manager.load_config()

            self.assertEqual(manager.ocr_pipeline_mode, "structure_default")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_structure_pipeline_config.py -q
```

Expected: FAIL because `ocr_pipeline_mode` does not exist or still defaults to the old mode.

- [ ] **Step 3: Implement config constants**

In `data_manager.py`, near `_DEFAULT_OCR_MODE`, add:

```python
_DEFAULT_OCR_PIPELINE_MODE = "structure_default"
_VALID_OCR_PIPELINE_MODES = {"structure_default", "legacy_hybrid"}


def _normalize_ocr_pipeline_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_OCR_PIPELINE_MODES:
        return normalized
    return _DEFAULT_OCR_PIPELINE_MODE
```

In `DataManager.__init__`, add:

```python
self.ocr_pipeline_mode = _DEFAULT_OCR_PIPELINE_MODE
```

In `load_config()`, after loading `ocr_mode`, add:

```python
self.ocr_pipeline_mode = _normalize_ocr_pipeline_mode(cfg.get("ocr_pipeline_mode"))
```

Update `save_config()` signature:

```python
def save_config(self, api_key=None, admin_pass=None, models=None, ocr_mode=None, ocr_pipeline_mode=None):
```

Inside `save_config()`, add:

```python
if ocr_pipeline_mode is not None:
    current_data["ocr_pipeline_mode"] = _normalize_ocr_pipeline_mode(ocr_pipeline_mode)
    self.ocr_pipeline_mode = current_data["ocr_pipeline_mode"]
```

- [ ] **Step 4: Run config tests**

```powershell
python -m pytest tests/test_structure_pipeline_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add data_manager.py tests/test_structure_pipeline_config.py
git commit -m "feat: default to structure OCR pipeline mode"
```

---

### Task 2: Settings UI Shows New Default And Legacy Option

**Files:**
- Modify: `admin_dialogs.py`
- Modify: `main_app_qt.py`
- Modify: `tests/test_admin_config_dialog.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_admin_config_dialog.py`:

```python
    def test_pipeline_mode_selector_defaults_to_structure_pipeline(self):
        dialog = AdminConfigDialog(None, {"api_key": "demo", "admin_password": "admin"})
        self.assertTrue(hasattr(dialog, "cb_ocr_pipeline_mode"))
        self.assertEqual(dialog.cb_ocr_pipeline_mode.currentData(), "structure_default")

    def test_pipeline_mode_selector_keeps_legacy_available(self):
        dialog = AdminConfigDialog(None, {"api_key": "demo", "admin_password": "admin"})
        index = dialog.cb_ocr_pipeline_mode.findData("legacy_hybrid")
        self.assertGreaterEqual(index, 0)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_admin_config_dialog.py -q
```

Expected: FAIL because the selector does not exist or uses old values.

- [ ] **Step 3: Add the selector to both AdminConfigDialog copies**

In both `admin_dialogs.py` and `main_app_qt.py`, add this under the existing local OCR runtime selector:

```python
grid_ocr.addWidget(QLabel("Pipeline OCR:"), 1, 0)
self.cb_ocr_pipeline_mode = QComboBox()
self.cb_ocr_pipeline_mode.addItem("Mới: PP-StructureV3 mặc định", "structure_default")
self.cb_ocr_pipeline_mode.addItem("Cũ: Paddle + Gemini", "legacy_hybrid")
current_pipeline_mode = getattr(app_data, "ocr_pipeline_mode", "structure_default")
current_pipeline_index = self.cb_ocr_pipeline_mode.findData(current_pipeline_mode)
self.cb_ocr_pipeline_mode.setCurrentIndex(current_pipeline_index if current_pipeline_index >= 0 else 0)
grid_ocr.addWidget(self.cb_ocr_pipeline_mode, 1, 1)
```

In each `_save()`, include:

```python
"ocr_pipeline_mode": self.cb_ocr_pipeline_mode.currentData() or "structure_default",
```

Store it in `file_data`:

```python
"ocr_pipeline_mode": config_data["ocr_pipeline_mode"],
```

Update runtime state:

```python
app_data.ocr_pipeline_mode = config_data["ocr_pipeline_mode"]
```

- [ ] **Step 4: Run UI tests**

```powershell
python -m pytest tests/test_admin_config_dialog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add admin_dialogs.py main_app_qt.py tests/test_admin_config_dialog.py
git commit -m "feat: expose structure OCR pipeline setting"
```

---

### Task 3: Add New PP-Structure Subprocess Runner

**Files:**
- Create: `ocr_structure_runner.py`
- Test: `tests/test_ocr_structure_runner.py`

- [ ] **Step 1: Write tests for result normalization helpers**

Create `tests/test_ocr_structure_runner.py`:

```python
import unittest

import ocr_structure_runner


class OcrStructureRunnerTests(unittest.TestCase):
    def test_make_safe_json_removes_non_serializable_values(self):
        data = {
            "text": "Cafe",
            "score": 0.91,
            "array_like": object(),
            "nested": {"value": 10},
        }

        safe = ocr_structure_runner._make_safe_json(data)

        self.assertEqual(safe["text"], "Cafe")
        self.assertEqual(safe["score"], 0.91)
        self.assertEqual(safe["nested"], {"value": 10})
        self.assertIsInstance(safe["array_like"], str)

    def test_build_output_has_required_top_level_keys(self):
        output = ocr_structure_runner._build_output([], elapsed_seconds=1.25)

        self.assertIn("pages", output)
        self.assertIn("raw_text", output)
        self.assertIn("avg_confidence", output)
        self.assertIn("elapsed_seconds", output)
        self.assertEqual(output["elapsed_seconds"], 1.25)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_ocr_structure_runner.py -q
```

Expected: FAIL because `ocr_structure_runner.py` does not exist.

- [ ] **Step 3: Implement runner**

Create `ocr_structure_runner.py`:

```python
import json
import logging
import os
import sys
import time
import warnings

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ.pop("FLAGS_selected_gpus", None)
warnings.filterwarnings("ignore")
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddleocr").setLevel(logging.ERROR)


def _make_safe_json(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _make_safe_json(v) for k, v in value.items()}
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
    candidates = [
        page_payload,
        page_payload.get("res", {}) if isinstance(page_payload, dict) else {},
        page_payload.get("overall_ocr_res", {}) if isinstance(page_payload, dict) else {},
    ]
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
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: ocr_structure_runner.py <image_path> <output_json_path>", file=sys.stderr)
        sys.exit(1)
    sys.exit(run_structure(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 4: Run runner tests**

```powershell
python -m pytest tests/test_ocr_structure_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add ocr_structure_runner.py tests/test_ocr_structure_runner.py
git commit -m "feat: add PP-Structure subprocess runner"
```

---

### Task 4: Add New App-Side PP-Structure Wrapper

**Files:**
- Create: `module_paddle_structure_ocr.py`
- Test: `tests/test_module_paddle_structure_ocr.py`

- [ ] **Step 1: Write wrapper tests**

Create `tests/test_module_paddle_structure_ocr.py`:

```python
import unittest

from module_paddle_structure_ocr import StructurePaddleOCREngine


class StructurePaddleOCREngineTests(unittest.TestCase):
    def test_completion_message_includes_engine_and_time(self):
        engine = StructurePaddleOCREngine()
        message = engine._build_completion_message(block_count=12, avg_confidence=0.875, elapsed_seconds=1.234)
        self.assertIn("PP-StructureV3", message)
        self.assertIn("12", message)
        self.assertIn("87.5%", message)
        self.assertIn("1.23s", message)

    def test_build_result_summary_is_compact(self):
        engine = StructurePaddleOCREngine()
        result = engine._build_result_summary({
            "pages": [{"a": 1}],
            "raw_text": "A",
            "avg_confidence": 0.9,
            "elapsed_seconds": 2.0,
        })
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(result["avg_confidence"], 0.9)
        self.assertEqual(result["raw_text"], "A")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_module_paddle_structure_ocr.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement wrapper**

Create `module_paddle_structure_ocr.py`:

```python
import json
import os
import subprocess
import tempfile
import time

from core_rate_limiter import EngineCancellationError
from path_utils import get_asset_path, get_root_dir


class StructurePaddleOCREngine:
    def __init__(self):
        self.python_env_dir = os.path.join(get_root_dir(), "env")
        self.python_exe = os.path.join(self.python_env_dir, "python.exe") if os.name == "nt" else os.path.join(self.python_env_dir, "bin", "python")
        self.runner_script = get_asset_path("ocr_structure_runner.py")

    def _build_start_message(self):
        return "Dang goi PP-StructureV3 pipeline rieng..."

    def _build_completion_message(self, block_count, avg_confidence, elapsed_seconds):
        return f"PP-StructureV3 doc duoc {block_count} khoi (Tin cay: {avg_confidence:.1%}) trong {elapsed_seconds:.2f}s"

    def _build_result_summary(self, data):
        return {
            "page_count": len(data.get("pages", []) or []),
            "avg_confidence": float(data.get("avg_confidence") or 0.0),
            "raw_text": data.get("raw_text") or "",
        }

    def extract_structure(self, image_input, stop_event=None, status_callback=None):
        if not os.path.exists(self.python_exe):
            raise RuntimeError("Moi truong OCR chua duoc cai dat. Hay chay Setup_Moi_Truong.bat.")
        if not os.path.exists(self.runner_script):
            raise RuntimeError("Khong tim thay ocr_structure_runner.py.")

        if status_callback:
            status_callback(self._build_start_message())

        image_path = image_input
        is_temp_image = False
        if not isinstance(image_input, str):
            import cv2
            fd, image_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            cv2.imwrite(image_path, image_input)
            is_temp_image = True

        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        started_at = time.perf_counter()

        try:
            process = subprocess.Popen(
                [self.python_exe, self.runner_script, image_path, output_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                startupinfo=startupinfo,
                env=env,
            )
            while True:
                if stop_event and stop_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise EngineCancellationError("STOP_REQUESTED")
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            _, stderr = process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"Loi PP-Structure subprocess (Code {process.returncode}):\n{stderr}")
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            elapsed = float(data.get("elapsed_seconds") or (time.perf_counter() - started_at))
            if status_callback:
                summary = self._build_result_summary(data)
                status_callback(self._build_completion_message(summary["page_count"], summary["avg_confidence"], elapsed))
            return data
        finally:
            if is_temp_image and image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError:
                    pass
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass


_structure_instance = None


def get_structure_paddle_engine():
    global _structure_instance
    if _structure_instance is None:
        _structure_instance = StructurePaddleOCREngine()
    return _structure_instance
```

- [ ] **Step 4: Run wrapper tests**

```powershell
python -m pytest tests/test_module_paddle_structure_ocr.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add module_paddle_structure_ocr.py tests/test_module_paddle_structure_ocr.py
git commit -m "feat: add PP-Structure app wrapper"
```

---

### Task 5: Normalize PP-Structure Results

**Files:**
- Create: `structure_result_normalizer.py`
- Test: `tests/test_structure_result_normalizer.py`

- [ ] **Step 1: Write tests**

Create `tests/test_structure_result_normalizer.py`:

```python
import unittest

from structure_result_normalizer import normalize_structure_result


class StructureResultNormalizerTests(unittest.TestCase):
    def test_normalize_collects_text_and_tables(self):
        result = {
            "raw_text": "Cafe\n1.250.000",
            "avg_confidence": 0.9,
            "pages": [
                {
                    "res": {
                        "layout_det_res": {"boxes": [{"label": "table", "score": 0.95, "coordinate": [1, 2, 3, 4]}]},
                        "overall_ocr_res": {"rec_texts": ["Cafe"], "rec_scores": [0.91]},
                    }
                }
            ],
        }

        normalized = normalize_structure_result(result)

        self.assertEqual(normalized["raw_text"], "Cafe\n1.250.000")
        self.assertEqual(normalized["avg_confidence"], 0.9)
        self.assertEqual(len(normalized["regions"]), 1)
        self.assertEqual(normalized["regions"][0]["label"], "table")
        self.assertEqual(normalized["tokens"][0]["text"], "Cafe")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_structure_result_normalizer.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement normalizer**

Create `structure_result_normalizer.py`:

```python
def _iter_page_dicts(result):
    for page in result.get("pages", []) or []:
        yield page if isinstance(page, dict) else {}


def _extract_regions(page):
    res = page.get("res", page)
    layout = res.get("layout_det_res", {}) if isinstance(res, dict) else {}
    boxes = layout.get("boxes", []) if isinstance(layout, dict) else []
    regions = []
    for index, box in enumerate(boxes):
        if not isinstance(box, dict):
            continue
        regions.append({
            "region_id": f"r_{index + 1:04d}",
            "label": str(box.get("label") or "unknown"),
            "confidence": float(box.get("score") or 0.0),
            "bbox": box.get("coordinate") or [],
        })
    return regions


def _extract_tokens(page):
    res = page.get("res", page)
    ocr = res.get("overall_ocr_res", {}) if isinstance(res, dict) else {}
    texts = ocr.get("rec_texts", []) if isinstance(ocr, dict) else []
    scores = ocr.get("rec_scores", []) if isinstance(ocr, dict) else []
    tokens = []
    for index, text in enumerate(texts):
        score = scores[index] if index < len(scores) else 0.0
        tokens.append({
            "token_id": f"t_{index + 1:04d}",
            "text": str(text).strip(),
            "confidence": float(score or 0.0),
        })
    return tokens


def normalize_structure_result(result):
    regions = []
    tokens = []
    for page in _iter_page_dicts(result):
        regions.extend(_extract_regions(page))
        tokens.extend(_extract_tokens(page))
    return {
        "raw_text": result.get("raw_text") or "",
        "avg_confidence": float(result.get("avg_confidence") or 0.0),
        "regions": regions,
        "tokens": tokens,
        "pages": result.get("pages", []) or [],
    }
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_structure_result_normalizer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add structure_result_normalizer.py tests/test_structure_result_normalizer.py
git commit -m "feat: normalize PP-Structure results"
```

---

### Task 6: Build Business KIE Using Data Structure Folder

**Files:**
- Create: `business_kie.py`
- Test: `tests/test_business_kie.py`

- [ ] **Step 1: Write tests for local KIE priors**

Create `tests/test_business_kie.py`:

```python
import unittest

from business_kie import BusinessKIE


class FakeDataStore:
    suppliers_dict = {"COHA": "Co Ha Tap Hoa"}
    suppliers_context_str = "COHA=Co Ha Tap Hoa (San pham: Dau an 25L, gas mini, duong)"
    items_by_code = {"bep153": {"code": "BEP153", "name": "Ca rot baby", "unit": "Gram", "group": "BEP01"}}
    items_dict = {"ca rot baby": {"code": "BEP153", "name": "Ca rot baby", "unit": "Gram", "group": "BEP01"}}
    aliases_dict = {"roots": {"code": "BEP153", "units": [{"unit": "Gram", "factor": 1.0}]}}
    kho_dict = {"BEP": "LH-BEP"}


class BusinessKIETests(unittest.TestCase):
    def test_supplier_infers_from_known_supplier_code_or_products(self):
        kie = BusinessKIE(FakeDataStore())
        result = kie.extract({"raw_text": "Co Ha Tap Hoa\nDau an 25L\nTong cong 250000", "tokens": []})
        self.assertEqual(result["supplier"]["supplier_name_code"], "COHA")

    def test_item_alias_maps_to_master_item_code(self):
        kie = BusinessKIE(FakeDataStore())
        result = kie.extract({"raw_text": "Roots\nTong cong 250000", "tokens": []})
        self.assertEqual(result["items"][0]["product_name"], "Ca rot baby")
        self.assertEqual(result["items"][0]["item_code"], "BEP153")

    def test_department_infers_from_item_group(self):
        kie = BusinessKIE(FakeDataStore())
        result = kie.extract({"raw_text": "Roots\nTong cong 250000", "tokens": []})
        self.assertEqual(result["transaction"]["department"], "BEP")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_business_kie.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement local KIE**

Create `business_kie.py`:

```python
import re


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _dept_from_group(group):
    value = str(group or "").upper()
    if value.startswith("BEP"):
        return "BEP"
    if value.startswith(("BAR", "RUOU", "CCDCBAR")):
        return "BAR"
    if value.startswith("BANH"):
        return "BANH"
    if value.startswith("RANG"):
        return "RANG"
    return None


class BusinessKIE:
    def __init__(self, data_store):
        self.data_store = data_store

    def _extract_supplier(self, text):
        cleaned = _clean(text)
        for code, name in getattr(self.data_store, "suppliers_dict", {}).items():
            if _clean(code) in cleaned or _clean(name) in cleaned:
                return {"supplier_name_code": code, "supplier_name_raw": name, "confidence": 0.95}
        context = getattr(self.data_store, "suppliers_context_str", "")
        for part in str(context).split("|"):
            if "=" not in part:
                continue
            code, rest = part.split("=", 1)
            code = code.strip()
            product_text = _clean(rest)
            hits = sum(1 for token in product_text.split(",") if token.strip() and _clean(token) in cleaned)
            if hits:
                return {"supplier_name_code": code, "supplier_name_raw": rest.split("(", 1)[0].strip(), "confidence": 0.72}
        return {"supplier_name_code": None, "supplier_name_raw": None, "confidence": 0.0}

    def _extract_items(self, text):
        cleaned = _clean(text)
        items = []
        aliases = getattr(self.data_store, "aliases_dict", {})
        for alias, info in aliases.items():
            if _clean(alias) in cleaned:
                code = str(info.get("code") or "").strip()
                record = getattr(self.data_store, "items_by_code", {}).get(code.lower(), {})
                items.append({
                    "item_code": code,
                    "product_name": record.get("name") or alias,
                    "unit": record.get("unit") or None,
                    "quantity": None,
                    "unit_price": None,
                    "total_price": None,
                    "confidence": 0.88,
                    "_group": record.get("group"),
                })
        if items:
            return items
        for name, record in getattr(self.data_store, "items_dict", {}).items():
            if _clean(name) in cleaned:
                items.append({
                    "item_code": record.get("code"),
                    "product_name": record.get("name") or name,
                    "unit": record.get("unit"),
                    "quantity": None,
                    "unit_price": None,
                    "total_price": None,
                    "confidence": 0.75,
                    "_group": record.get("group"),
                })
        return items

    def extract(self, normalized_structure):
        text = normalized_structure.get("raw_text") or ""
        supplier = self._extract_supplier(text)
        items = self._extract_items(text)
        department = None
        for item in items:
            department = _dept_from_group(item.get("_group"))
            if department:
                break
        for item in items:
            item.pop("_group", None)
        return {
            "supplier": supplier,
            "transaction": {"department": department},
            "items": items,
            "totals": {},
            "warnings": [],
        }
```

- [ ] **Step 4: Run KIE tests**

```powershell
python -m pytest tests/test_business_kie.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add business_kie.py tests/test_business_kie.py
git commit -m "feat: add business KIE from master data"
```

---

### Task 7: Build Invoice JSON And Validation

**Files:**
- Create: `invoice_json_builder.py`
- Create: `invoice_validation.py`
- Test: `tests/test_structure_invoice_json.py`

- [ ] **Step 1: Write tests**

Create `tests/test_structure_invoice_json.py`:

```python
import unittest

from invoice_json_builder import build_invoice_json
from invoice_validation import validate_invoice_json


class StructureInvoiceJsonTests(unittest.TestCase):
    def test_build_invoice_json_matches_downstream_schema(self):
        invoice = build_invoice_json(
            kie_result={
                "supplier": {"supplier_name_code": "COHA", "supplier_name_raw": "Co Ha Tap Hoa", "confidence": 0.9},
                "transaction": {"department": "BEP"},
                "items": [{"product_name": "Ca rot baby", "unit": "Gram", "quantity": 1, "unit_price": 250000, "total_price": 250000}],
                "totals": {"total_amount": 250000},
                "warnings": [],
            },
            confidence_score=0.88,
        )

        self.assertEqual(invoice["supplier_info"]["supplier_name_code"], "COHA")
        self.assertEqual(invoice["transaction_info"]["department"], "BEP")
        self.assertEqual(invoice["items"][0]["product_name"], "Ca rot baby")
        self.assertEqual(invoice["totals"]["total_amount"], 250000)

    def test_validation_passes_when_supplier_item_and_total_exist(self):
        invoice = build_invoice_json(
            kie_result={
                "supplier": {"supplier_name_code": "COHA", "supplier_name_raw": "Co Ha Tap Hoa", "confidence": 0.9},
                "transaction": {"department": "BEP"},
                "items": [{"product_name": "Ca rot baby", "unit": "Gram", "quantity": 1, "unit_price": 250000, "total_price": 250000}],
                "totals": {"total_amount": 250000},
                "warnings": [],
            },
            confidence_score=0.88,
        )

        report = validate_invoice_json(invoice)

        self.assertTrue(report["can_use_local_result"])
        self.assertEqual(report["status"], "pass")
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_structure_invoice_json.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement JSON builder**

Create `invoice_json_builder.py`:

```python
def build_invoice_json(kie_result, confidence_score):
    supplier = kie_result.get("supplier", {}) or {}
    transaction = kie_result.get("transaction", {}) or {}
    totals = kie_result.get("totals", {}) or {}
    return {
        "document_info": {
            "recommended_model": "PPStructureV3",
            "invoice_type": "STRUCTURE_EXTRACTED",
            "confidence_score": float(round(confidence_score, 3)),
        },
        "supplier_info": {
            "supplier_name_raw": supplier.get("supplier_name_raw"),
            "supplier_name_code": supplier.get("supplier_name_code"),
            "tax_id": supplier.get("tax_id"),
        },
        "transaction_info": {
            "invoice_number": transaction.get("invoice_number"),
            "invoice_date": transaction.get("invoice_date"),
            "department": transaction.get("department"),
            "buyer_name": transaction.get("buyer_name"),
            "delivery_location": transaction.get("delivery_location"),
            "raw_discount_info": transaction.get("raw_discount_info"),
            "raw_shipping_fee_info": transaction.get("raw_shipping_fee_info"),
            "raw_payment_method": transaction.get("raw_payment_method"),
        },
        "items": [
            {
                "product_name": item.get("product_name"),
                "unit": item.get("unit"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "total_price": item.get("total_price"),
                "raw_vat_rate": item.get("raw_vat_rate"),
                "raw_vat_amount": item.get("raw_vat_amount"),
            }
            for item in (kie_result.get("items") or [])
        ],
        "totals": {
            "sub_total": totals.get("sub_total", 0),
            "vat_percentage": totals.get("vat_percentage", 0),
            "vat_amount": totals.get("vat_amount", 0),
            "total_amount": totals.get("total_amount", 0),
        },
        "_structure_pipeline": {
            "warnings": kie_result.get("warnings", []),
            "fallback_used": False,
        },
    }
```

Create `invoice_validation.py`:

```python
def _has_value(value):
    return value not in (None, "", [], {})


def validate_invoice_json(invoice_json):
    missing = []
    if not _has_value((invoice_json.get("supplier_info") or {}).get("supplier_name_code")):
        missing.append("supplier_name_code")
    if not invoice_json.get("items"):
        missing.append("items")
    if not _has_value((invoice_json.get("totals") or {}).get("total_amount")):
        missing.append("total_amount")
    confidence = invoice_json.get("document_info", {}).get("confidence_score", 0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    can_use = not missing and confidence >= 0.70
    return {
        "status": "pass" if can_use else "warning",
        "can_use_local_result": can_use,
        "missing_required_fields": missing,
        "confidence": confidence,
    }
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_structure_invoice_json.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add invoice_json_builder.py invoice_validation.py tests/test_structure_invoice_json.py
git commit -m "feat: build and validate structure invoice JSON"
```

---

### Task 8: Add Light Model Fallback For Weak Local Extraction

**Files:**
- Create: `fallback_light_structurer.py`
- Test: `tests/test_fallback_light_structurer.py`

- [ ] **Step 1: Write tests**

Create `tests/test_fallback_light_structurer.py`:

```python
import unittest

from fallback_light_structurer import should_use_light_fallback, build_light_fallback_text


class FallbackLightStructurerTests(unittest.TestCase):
    def test_should_use_light_fallback_when_validation_fails(self):
        self.assertTrue(should_use_light_fallback({"can_use_local_result": False}))
        self.assertFalse(should_use_light_fallback({"can_use_local_result": True}))

    def test_build_light_fallback_text_includes_structure_context(self):
        text = build_light_fallback_text({
            "raw_text": "Cafe\nTong cong 250000",
            "regions": [{"label": "table", "bbox": [1, 2, 3, 4]}],
            "tokens": [{"text": "Cafe", "confidence": 0.9}],
        })

        self.assertIn("RAW_TEXT", text)
        self.assertIn("REGIONS", text)
        self.assertIn("TOKENS", text)
        self.assertIn("Cafe", text)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_fallback_light_structurer.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement fallback helper**

Create `fallback_light_structurer.py`:

```python
import json


def should_use_light_fallback(validation_report):
    return not bool(validation_report.get("can_use_local_result"))


def build_light_fallback_text(normalized_structure):
    compact = {
        "raw_text": normalized_structure.get("raw_text") or "",
        "regions": normalized_structure.get("regions") or [],
        "tokens": normalized_structure.get("tokens") or [],
    }
    return (
        "RAW_TEXT:\n"
        f"{compact['raw_text']}\n\n"
        "REGIONS:\n"
        f"{json.dumps(compact['regions'], ensure_ascii=False)}\n\n"
        "TOKENS:\n"
        f"{json.dumps(compact['tokens'], ensure_ascii=False)}"
    )


def run_light_fallback(normalized_structure, avg_confidence, api_key, data_store, stop_event=None, status_callback=None):
    from module_flash_ocr import get_flash_structurer

    fallback_text = build_light_fallback_text(normalized_structure)
    flash_engine = get_flash_structurer(api_key, data_store)
    result = flash_engine.structure_text_to_json(
        fallback_text,
        avg_confidence,
        stop_event=stop_event,
        status_callback=status_callback,
    )
    result.setdefault("_structure_pipeline", {})
    result["_structure_pipeline"]["fallback_used"] = True
    return result
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_fallback_light_structurer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add fallback_light_structurer.py tests/test_fallback_light_structurer.py
git commit -m "feat: add light fallback for structure pipeline"
```

---

### Task 9: Create Separate Folder Pipeline

**Files:**
- Create: `ocr_pipeline_structure.py`
- Test: `tests/test_ocr_pipeline_structure.py`

- [ ] **Step 1: Write smoke tests for pipeline decisions**

Create `tests/test_ocr_pipeline_structure.py`:

```python
import unittest

from ocr_pipeline_structure import _should_keep_processing


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
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
python -m pytest tests/test_ocr_pipeline_structure.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement new pipeline**

Create `ocr_pipeline_structure.py` with a separate `run_pipeline()` function. Use this control flow:

```python
def _should_keep_processing(stop_event):
    return not (stop_event and stop_event.is_set())
```

Inside `run_pipeline(input_dir, stop_event, api_key, signals)`:

```text
1. Load app_data.
2. Iterate images in input folder.
3. Use image_processor.prepare_image.
4. Convert image to OpenCV BGR.
5. Call get_structure_paddle_engine().extract_structure.
6. normalize_structure_result.
7. BusinessKIE(app_data).extract.
8. build_invoice_json.
9. enrich_supplier before validation.
10. validate_invoice_json.
11. If validation fails, call run_light_fallback and run enrich_supplier again on fallback JSON.
12. Always call module_calculator.get_calculator(...).run_calculation.
13. Save final JSON to DONE.
14. Move processed image to DONE only after success.
15. At end, call core_excel_mapper.append_invoices_to_excel.
```

The implementation may copy orchestration patterns from `ocr_pipeline.py`, but it must not call `get_paddle_engine()` and must not import `module_paddle_ocr.py`.

- [ ] **Step 4: Run pipeline smoke tests**

```powershell
python -m pytest tests/test_ocr_pipeline_structure.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add ocr_pipeline_structure.py tests/test_ocr_pipeline_structure.py
git commit -m "feat: add separate structure OCR folder pipeline"
```

---

### Task 10: Make App Use New Pipeline By Default

**Files:**
- Modify: `main_app_qt.py`

- [ ] **Step 1: Update OCRWorker routing**

Inside `OCRWorker._run_pipeline()` or the equivalent scan entry, route by `app_data.ocr_pipeline_mode`:

```python
from data_manager import app_data

if getattr(app_data, "ocr_pipeline_mode", "structure_default") == "legacy_hybrid":
    from ocr_pipeline import run_pipeline as run_legacy_pipeline
    self._output_path = run_legacy_pipeline(self.input_dir, self.stop_event, self.api_key, self.s)
    return

from ocr_pipeline_structure import run_pipeline as run_structure_pipeline
self._output_path = run_structure_pipeline(self.input_dir, self.stop_event, self.api_key, self.s)
return
```

This task may leave the old inline worker body in place temporarily if removing it is too risky, but the active default path must call `ocr_pipeline_structure.run_pipeline()`.

- [ ] **Step 2: Run focused tests**

```powershell
python -m pytest tests/test_structure_pipeline_config.py tests/test_admin_config_dialog.py tests/test_ocr_pipeline_structure.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```powershell
git add main_app_qt.py
git commit -m "feat: use structure OCR pipeline by default"
```

---

### Task 11: Setup And Packaging

**Files:**
- Modify: `Setup_Moi_Truong.bat`
- Modify: `Setup_Nguon.bat`
- Modify: `LighthouseOCR.spec`
- Modify: `README.md`

- [ ] **Step 1: Update PaddleOCR install command**

In both setup scripts, replace the current PaddleOCR install line with:

```bat
"%PYTHON_EXE%" -m pip install "paddleocr[doc-parser]==3.6.0"
```

Use `paddlepaddle==3.2.0` from the Paddle CPU index. In this Windows CPU environment, 3.3.1 installed but failed during PP-Structure inference.

- [ ] **Step 2: Add structure runner to packaging if needed**

Check `LighthouseOCR.spec`. If individual Python files are explicitly listed as data files, add:

```python
("ocr_structure_runner.py", "."),
```

If the spec bundles all project `.py` files automatically, do not add duplicate entries.

- [ ] **Step 3: Update README**

Add a short note:

```markdown
Default OCR pipeline: PP-StructureV3 + PP-OCRv5 local extraction, with Gemini Flash only as fallback when local validation is weak. Legacy Paddle + Gemini mode remains selectable in system settings.
```

- [ ] **Step 4: Commit**

```powershell
git add Setup_Moi_Truong.bat Setup_Nguon.bat LighthouseOCR.spec README.md
git commit -m "chore: install PP-Structure pipeline dependencies"
```

---

### Task 12: Disk Usage Guard

**Files:**
- Modify: `ocr_structure_runner.py`
- Test: `tests/test_ocr_structure_runner.py`

- [ ] **Step 1: Add test that output does not contain image bytes**

Append to `tests/test_ocr_structure_runner.py`:

```python
    def test_output_has_no_debug_image_fields(self):
        output = ocr_structure_runner._build_output([], elapsed_seconds=0.1)
        text = str(output).lower()
        self.assertNotIn("image_base64", text)
        self.assertNotIn("outputimages", text)
```

- [ ] **Step 2: Ensure runner uses visualize false**

Verify this exact call exists:

```python
result = pipeline.predict(image_path, visualize=False)
```

Do not call:

```python
res.save_to_img(...)
res.save_to_json(...)
res.save_to_markdown(...)
res.save_to_word(...)
```

- [ ] **Step 3: Run tests**

```powershell
python -m pytest tests/test_ocr_structure_runner.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add ocr_structure_runner.py tests/test_ocr_structure_runner.py
git commit -m "test: prevent structure pipeline debug file growth"
```

---

### Task 13: Verification

**Files:**
- Read-only verification.

- [ ] **Step 1: Run focused tests**

```powershell
python -m pytest tests/test_structure_pipeline_config.py tests/test_admin_config_dialog.py tests/test_ocr_structure_runner.py tests/test_module_paddle_structure_ocr.py tests/test_structure_result_normalizer.py tests/test_business_kie.py tests/test_structure_invoice_json.py tests/test_fallback_light_structurer.py tests/test_ocr_pipeline_structure.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full tests**

```powershell
python -m pytest tests -q
```

Expected: PASS, except for pre-existing environment-only failures unrelated to this change.

- [ ] **Step 3: Verify old modules were not changed**

```powershell
git diff -- module_paddle_ocr.py ocr_runner.py
```

Expected: no diff.

- [ ] **Step 4: Verify multilingual text**

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from pathlib import Path
paths = [
    "admin_dialogs.py",
    "main_app_qt.py",
    "data_manager.py",
    "docs/superpowers/plans/2026-06-03-advanced-paddle-pipeline-toggle.md",
]
for path in paths:
    text = Path(path).read_text(encoding="utf-8")
    assert "\ufffd" not in text, path
    assert "Paddle" in text or "OCR" in text, path
print("encoding check passed")
'@ | python -
```

Expected: `encoding check passed`.

- [ ] **Step 5: Manual smoke test**

Run app and confirm:

```text
System settings default: "Mới: PP-StructureV3 mặc định"
Scan button uses the new structure pipeline.
If local extraction is weak, log shows light fallback.
DONE folder contains final JSON and processed image, not PP-Structure debug images.
Legacy mode can still be selected and run separately.
```

---

## Self-Review

- Old Paddle module isolation: plan does not modify `module_paddle_ocr.py` or `ocr_runner.py`.
- Default route: new PP-Structure pipeline is the default through `ocr_pipeline_mode = "structure_default"`.
- KIE: uses `DataManager` and the existing `Data structure` files as local business knowledge.
- Supplier enrichment: missing NCC is resolved before calculator only when local item evidence is strong; weak evidence leaves NCC empty and records `_supplier_resolution`.
- Calculator boundary: `module_calculator.py` does not call LLM just to infer NCC. It owns financial normalization only.
- Fallback: Gemini Flash light model is used only when validation says local extraction is weak.
- Disk usage: runner uses `visualize=False`, no save-to-image/Markdown/DOCX calls, and temp files are deleted.
- Downstream compatibility: final JSON still matches the schema used by calculator, Excel mapper, and review UI.
