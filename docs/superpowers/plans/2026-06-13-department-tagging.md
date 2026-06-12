# Department Tagging Dialog + Pro Vision Escalation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mandatory pre-scan dialog that tags each invoice image to a department (BEP/BAR/BANH/RANG), feed that department authoritatively into the pipeline + LLM prompts, and widen Pro Vision escalation to rescue weak/handwritten results.

**Architecture:** A small Qt dialog (thin view over a headless `TaggingState`) runs before the OCR worker and yields a `{filename → dept}` map. `run_pipeline` injects the dept into `transaction_info.department` (already consumed by the Excel mapper) and into the light/Pro fallback prompts. A new additive predicate escalates weak results (garbled names / total mismatch / handwritten+low-confidence) to Pro Vision.

**Tech Stack:** Python 3, PyQt5, pytest. Existing modules: `ocr_pipeline_structure.py`, `module_flash_ocr.py`, `module_pro_ocr.py`, `fallback_light_structurer.py`, `main_app_qt.py`.

**Spec:** `docs/superpowers/specs/2026-06-13-department-tagging-design.md`

**Conventions:** Run tests with `python -m pytest` from the project root `D:\Working\Lighthouse OCR Nhap hang`. Commit after each task. Stay on the current branch `feature/output-run-folders-json-browser` (per user). Commit only the files listed in each task's commit step (the branch has unrelated uncommitted work — never `git add -A`).

---

### Task 1: `departments.py` — shared constants + prompt line

**Files:**
- Create: `departments.py`
- Test: `tests/test_departments.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_departments.py
from departments import VALID_DEPARTMENTS, department_prompt_line


def test_valid_departments_exact_set():
    assert VALID_DEPARTMENTS == ("BEP", "BAR", "BANH", "RANG")


def test_prompt_line_for_valid_dept_mentions_dept():
    line = department_prompt_line("BEP")
    assert "BEP" in line
    assert "bộ phận" in line.lower()
    assert line.endswith("\n\n")


def test_prompt_line_normalizes_case_and_whitespace():
    assert "BAR" in department_prompt_line("  bar ")


def test_prompt_line_empty_for_invalid_dept():
    assert department_prompt_line("XYZ") == ""
    assert department_prompt_line("") == ""
    assert department_prompt_line(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_departments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'departments'`

- [ ] **Step 3: Write minimal implementation**

```python
# departments.py
"""Shared department constants and prompt helpers.

Kept dependency-free (no Qt, no heavy imports) so both the Qt tagging dialog
and the headless OCR pipeline can import it.
"""

VALID_DEPARTMENTS = ("BEP", "BAR", "BANH", "RANG")


def department_prompt_line(dept) -> str:
    """Return a one-block LLM prompt prefix telling the model the invoice's
    department, or "" when dept is not one of the 4 valid codes."""
    dept = str(dept or "").strip().upper()
    if dept not in VALID_DEPARTMENTS:
        return ""
    return (
        "DEPARTMENT_CONTEXT:\n"
        f"Hóa đơn này thuộc bộ phận [{dept}]. "
        "Ưu tiên đọc tên hàng theo nhóm hàng của bộ phận này.\n\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_departments.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add departments.py tests/test_departments.py
git commit -m "feat: add departments module (valid set + LLM prompt line)"
```

---

### Task 2: `TaggingState` — headless tagging core

**Files:**
- Create: `department_tagging_dialog.py` (only the `TaggingState` class in this task)
- Test: `tests/test_tagging_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tagging_state.py
from department_tagging_dialog import TaggingState


def test_assign_sets_and_advances_to_next():
    s = TaggingState(["a.jpg", "b.jpg", "c.jpg"])
    assert s.current_filename() == "a.jpg"
    assert s.assign("BEP") is True
    assert s.department_of("a.jpg") == "BEP"
    assert s.current_filename() == "b.jpg"


def test_assign_normalizes_case():
    s = TaggingState(["a.jpg"])
    s.assign("bep")
    assert s.department_of("a.jpg") == "BEP"


def test_invalid_dept_rejected():
    s = TaggingState(["a.jpg"])
    assert s.assign("XYZ") is False
    assert s.department_of("a.jpg") is None
    assert s.current_filename() == "a.jpg"


def test_advance_skips_already_assigned():
    s = TaggingState(["a.jpg", "b.jpg", "c.jpg"])
    s.goto(1)
    s.assign("BAR")          # b assigned -> advance to c
    assert s.current_filename() == "c.jpg"
    s.assign("BEP")          # c assigned -> wrap to a (still unassigned)
    assert s.current_filename() == "a.jpg"


def test_assign_last_unassigned_stays_put():
    s = TaggingState(["a.jpg", "b.jpg"])
    s.assign("BEP")          # -> b
    s.assign("BAR")          # all assigned, stay on b
    assert s.current_filename() == "b.jpg"
    assert s.is_complete()


def test_back_forward_goto_bounds():
    s = TaggingState(["a.jpg", "b.jpg"])
    s.back()                 # already at 0, no-op
    assert s.current_filename() == "a.jpg"
    s.forward()
    assert s.current_filename() == "b.jpg"
    s.forward()              # at end, no-op
    assert s.current_filename() == "b.jpg"
    s.goto(0)
    assert s.current_filename() == "a.jpg"
    s.goto(99)               # out of range, no-op
    assert s.current_filename() == "a.jpg"


def test_is_complete_and_counts():
    s = TaggingState(["a.jpg", "b.jpg"])
    assert not s.is_complete()
    assert s.remaining() == 2
    s.assign("BEP")
    assert s.assigned_count() == 1
    assert not s.is_complete()
    s.assign("BAR")
    assert s.is_complete()
    assert s.remaining() == 0


def test_get_department_map_keyed_by_filename():
    s = TaggingState(["a.jpg", "b.jpg"])
    s.assign("BEP")
    s.assign("RANG")
    assert s.get_department_map() == {"a.jpg": "BEP", "b.jpg": "RANG"}


def test_empty_state_is_not_complete():
    s = TaggingState([])
    assert not s.is_complete()
    assert s.current_filename() is None
    assert s.assign("BEP") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tagging_state.py -v`
Expected: FAIL with `ImportError`/`ModuleNotFoundError` (file or class missing)

- [ ] **Step 3: Write minimal implementation**

Create `department_tagging_dialog.py` with ONLY this at the top (the Qt dialog is added in Task 7):

```python
# department_tagging_dialog.py
"""Pre-scan department tagging: headless TaggingState core + Qt dialog view.

The TaggingState class has no Qt dependency so it is unit-testable. The
DepartmentTaggingDialog (added later) is a thin view over it.
"""

from departments import VALID_DEPARTMENTS


class TaggingState:
    """Ordered list of image filenames + their department assignments."""

    def __init__(self, filenames):
        self.filenames = list(filenames)
        self.assignments = {}          # filename -> dept (UPPER, valid only)
        self.current_index = 0

    @property
    def total(self):
        return len(self.filenames)

    def current_filename(self):
        if not self.filenames:
            return None
        return self.filenames[self.current_index]

    def _next_unassigned_index(self):
        n = self.total
        for offset in range(1, n + 1):
            idx = (self.current_index + offset) % n
            if self.filenames[idx] not in self.assignments:
                return idx
        return None

    def assign(self, dept):
        dept = str(dept or "").strip().upper()
        if dept not in VALID_DEPARTMENTS:
            return False
        fn = self.current_filename()
        if fn is None:
            return False
        self.assignments[fn] = dept
        nxt = self._next_unassigned_index()
        if nxt is not None:
            self.current_index = nxt
        return True

    def back(self):
        if self.current_index > 0:
            self.current_index -= 1

    def forward(self):
        if self.current_index < self.total - 1:
            self.current_index += 1

    def goto(self, index):
        if 0 <= index < self.total:
            self.current_index = index

    def department_of(self, filename):
        return self.assignments.get(filename)

    def assigned_count(self):
        return len(self.assignments)

    def remaining(self):
        return self.total - self.assigned_count()

    def is_complete(self):
        return self.total > 0 and all(
            fn in self.assignments for fn in self.filenames
        )

    def get_department_map(self):
        return dict(self.assignments)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tagging_state.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add department_tagging_dialog.py tests/test_tagging_state.py
git commit -m "feat: add headless TaggingState for department tagging"
```

---

### Task 3: Pro Vision escalation predicate (pure logic)

**Files:**
- Modify: `ocr_pipeline_structure.py` (add helpers near the top, after `_should_use_vision_after_light_fallback` at line 30-31)
- Test: `tests/test_escalation_predicate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_escalation_predicate.py
from ocr_pipeline_structure import (
    _is_garbled_name,
    _garbled_name_ratio,
    _has_total_mismatch,
    _looks_handwritten,
    _should_escalate_weak_result,
)


def _inv(items=None, invoice_type="VAT_INVOICE", number="X1", date="2026-05-23",
         total_warning=None):
    j = {
        "document_info": {"invoice_type": invoice_type},
        "transaction_info": {"invoice_number": number, "invoice_date": date},
        "items": [{"product_name": n} for n in (items or [])],
        "totals": {},
    }
    if total_warning:
        j["totals"]["total_discrepancy_warning"] = total_warning
    return j


def test_is_garbled_name_flags_junk():
    for bad in ["cāB", "B'd", "xutg", "10Hinh", 'chuo"', "", "B"]:
        assert _is_garbled_name(bad) is True, bad


def test_is_garbled_name_accepts_legit():
    for ok in ["BO XAY", "UC GA", "Ba rọi xông khói Tasany 3mm",
               "Khoai tây Hychoice AAA XLF straight cut 1kg", "NAM"]:
        assert _is_garbled_name(ok) is False, ok


def test_garbled_ratio_r12_like_over_threshold():
    names = ["chua", "Mam", "cāB", "Bap", "chio", "pau",
             "Duo Bi", "xutg", "B'd", "10Hinh"]
    assert _garbled_name_ratio(_inv(names)) >= 0.30


def test_garbled_ratio_clean_printed_is_zero():
    names = ["Ba rọi xông khói Tasany 3mm",
             "Khoai tây Hychoice AAA XLF straight cut 1kg"]
    assert _garbled_name_ratio(_inv(names)) == 0.0


def test_total_mismatch_detected():
    assert _has_total_mismatch(_inv(total_warning="[CẢNH BÁO: lệch 80%]")) is True
    assert _has_total_mismatch(_inv()) is False


def test_looks_handwritten_by_type_or_missing_header():
    assert _looks_handwritten(_inv(invoice_type="HANDWRITTEN_INVOICE")) is True
    assert _looks_handwritten(_inv(invoice_type="RETAIL_INVOICE")) is True
    assert _looks_handwritten(_inv(number="", date="")) is True
    assert _looks_handwritten(_inv(invoice_type="VAT_INVOICE")) is False


def test_escalate_true_for_weak_cases():
    # r12: mislabeled VAT but garbled names
    r12 = _inv(["cāB", "xutg", "B'd", "10Hinh", "chua"], invoice_type="VAT_INVOICE")
    assert _should_escalate_weak_result(r12, {"confidence": 0.86}) is True
    # total mismatch
    r10 = _inv(["cad", "Nam"], invoice_type="HANDWRITTEN_INVOICE",
               total_warning="[CẢNH BÁO]")
    assert _should_escalate_weak_result(r10, {"confidence": 0.865}) is True
    # handwritten + low confidence, names not garbled
    hw = _inv(["Cà chua", "Bắp"], invoice_type="HANDWRITTEN_INVOICE")
    assert _should_escalate_weak_result(hw, {"confidence": 0.86}) is True


def test_escalate_false_for_clean_printed():
    printed = _inv(["Ba rọi xông khói Tasany 3mm",
                    "Khoai tây Hychoice AAA XLF straight cut 1kg"],
                   invoice_type="VAT_INVOICE", number="DO-1", date="2026-05-23")
    assert _should_escalate_weak_result(printed, {"confidence": 0.881}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_escalation_predicate.py -v`
Expected: FAIL with `ImportError: cannot import name '_is_garbled_name'`

- [ ] **Step 3: Write minimal implementation**

In `ocr_pipeline_structure.py`, insert after line 31 (right after `_should_use_vision_after_light_fallback`):

```python
# --- Weak-result escalation (handwriting / garbled / total mismatch) ---
WEAK_HANDWRITTEN_CONF = 0.90
WEAK_ANY_CONF = 0.80
GARBLED_NAME_RATIO = 0.30

_VOWELS = set(
    "aeiouy"
    "àáảãạăằắẳẵặâầấẩẫậ"
    "èéẻẽẹêềếểễệ"
    "ìíỉĩị"
    "òóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữự"
    "ỳýỷỹỵ"
)


def _is_garbled_name(name) -> bool:
    raw = str(name or "").strip()
    if not raw:
        return True
    if any(ch in raw for ch in ("'", '"', "`", "\\")):
        return True
    if re.match(r"^\d", raw):                 # item names virtually never start with a digit
        return True
    alpha = re.sub(r"[^a-zà-ỹ]", "", raw.lower())
    if len(alpha) <= 2:                       # essentially no readable word left
        return True
    if not any(ch in _VOWELS for ch in alpha):   # vowel-less gibberish
        return True
    return False


def _garbled_name_ratio(invoice_json) -> float:
    items = invoice_json.get("items") or []
    if not items:
        return 0.0
    garbled = sum(1 for it in items if _is_garbled_name(it.get("product_name")))
    return garbled / len(items)


def _has_total_mismatch(invoice_json) -> bool:
    totals = invoice_json.get("totals") or {}
    return bool(str(totals.get("total_discrepancy_warning") or "").strip())


def _looks_handwritten(invoice_json) -> bool:
    doc = invoice_json.get("document_info") or {}
    itype = str(doc.get("invoice_type") or "").upper()
    if "HANDWRITTEN" in itype or "RETAIL" in itype:
        return True
    txn = invoice_json.get("transaction_info") or {}
    no_number = not str(txn.get("invoice_number") or "").strip()
    no_date = not str(txn.get("invoice_date") or "").strip()
    return no_number and no_date


def _should_escalate_weak_result(invoice_json, validation_report) -> bool:
    if _has_total_mismatch(invoice_json):
        return True
    if _garbled_name_ratio(invoice_json) >= GARBLED_NAME_RATIO:
        return True
    conf = _validation_confidence(validation_report)
    if _looks_handwritten(invoice_json) and conf < WEAK_HANDWRITTEN_CONF:
        return True
    if conf < WEAK_ANY_CONF:
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_escalation_predicate.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline_structure.py tests/test_escalation_predicate.py
git commit -m "feat: weak-result Pro Vision escalation predicate"
```

---

### Task 4: `_apply_department_override` helper

**Files:**
- Modify: `ocr_pipeline_structure.py` (add helper after the escalation helpers from Task 3)
- Test: `tests/test_department_override.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_department_override.py
from ocr_pipeline_structure import _apply_department_override


def test_sets_department_and_source():
    j = {}
    _apply_department_override(j, "BEP")
    assert j["transaction_info"]["department"] == "BEP"
    assert j["_department_source"] == "user_tag"


def test_normalizes_case():
    j = {"transaction_info": {}}
    _apply_department_override(j, " bar ")
    assert j["transaction_info"]["department"] == "BAR"


def test_invalid_dept_ignored():
    j = {"transaction_info": {"department": "OLD"}}
    _apply_department_override(j, "XYZ")
    assert j["transaction_info"]["department"] == "OLD"
    assert "_department_source" not in j


def test_none_ignored():
    j = {}
    _apply_department_override(j, None)
    assert j == {}


def test_idempotent_and_reappliable_on_fresh_json():
    j1 = {}
    _apply_department_override(j1, "RANG")
    _apply_department_override(j1, "RANG")
    assert j1["transaction_info"]["department"] == "RANG"
    # simulate a fresh JSON returned by a fallback
    j2 = {"transaction_info": {"department": None}}
    _apply_department_override(j2, "RANG")
    assert j2["transaction_info"]["department"] == "RANG"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_department_override.py -v`
Expected: FAIL with `ImportError: cannot import name '_apply_department_override'`

- [ ] **Step 3: Write minimal implementation**

In `ocr_pipeline_structure.py`, add after the escalation helpers (and add the import at top of file: change line 3-4 area so `from departments import VALID_DEPARTMENTS` is present near the other top imports):

At the top of the file, after `import time` (line 4), add:

```python
from departments import VALID_DEPARTMENTS
```

Then add the helper:

```python
def _apply_department_override(invoice_json, dept):
    """Authoritatively set the user-tagged department on the invoice JSON.

    No-op when dept is not one of the 4 valid codes. Safe to call repeatedly
    and on a fresh JSON returned by a fallback."""
    dept = str(dept or "").strip().upper()
    if dept not in VALID_DEPARTMENTS:
        return invoice_json
    txn = invoice_json.setdefault("transaction_info", {})
    txn["department"] = dept
    invoice_json["_department_source"] = "user_tag"
    return invoice_json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_department_override.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline_structure.py tests/test_department_override.py
git commit -m "feat: _apply_department_override helper for user-tagged dept"
```

---

### Task 5: Inject `department_hint` into LLM prompts

**Files:**
- Modify: `module_flash_ocr.py:48,52`
- Modify: `module_pro_ocr.py:48,58`
- Modify: `fallback_light_structurer.py:27-37`
- Modify: `ocr_pipeline_structure.py:169-187` (`_run_pro_vision_fallback`)

No new unit test (these call the network LLM). The prompt-prefix builder is already covered by `tests/test_departments.py`. Verify by reading the diffs; behavior covered by manual run + Task 6 pipeline test.

- [ ] **Step 1: `module_flash_ocr.py` — accept + prepend dept context**

Change the method signature at line 48:

```python
    def structure_text_to_json(self, raw_paddle_text: str, avg_confidence: float, stop_event=None, status_callback=None, department_hint: str = None) -> dict:
```

Change line 52 from:

```python
        combined_prompt = f"{self.prompt_template}\n\nRAW_TEXT_INPUT_FROM_PADDLEOCR:\n{raw_paddle_text}"
```

to:

```python
        from departments import department_prompt_line
        dept_ctx = department_prompt_line(department_hint)
        combined_prompt = f"{dept_ctx}{self.prompt_template}\n\nRAW_TEXT_INPUT_FROM_PADDLEOCR:\n{raw_paddle_text}"
```

- [ ] **Step 2: `module_pro_ocr.py` — accept + prepend dept context**

Change the method signature at line 48:

```python
    def extract_image_directly(self, image: Image.Image, stop_event=None, status_callback=None, department_hint: str = None) -> dict:
```

Change the `contents_fn` at line 58 from:

```python
            contents_fn=lambda _: [self.prompt_template, image],
```

to:

```python
            contents_fn=lambda _: [f"{department_prompt_line(department_hint)}{self.prompt_template}", image],
```

And add this import inside `extract_image_directly` right after the `status_callback` block (after line 50):

```python
        from departments import department_prompt_line
```

- [ ] **Step 3: `fallback_light_structurer.py` — thread the hint**

Change `run_light_fallback` (lines 27-37) from:

```python
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
```

to:

```python
def run_light_fallback(normalized_structure, avg_confidence, api_key, data_store, stop_event=None, status_callback=None, department_hint=None):
    from module_flash_ocr import get_flash_structurer

    fallback_text = build_light_fallback_text(normalized_structure)
    flash_engine = get_flash_structurer(api_key, data_store)
    result = flash_engine.structure_text_to_json(
        fallback_text,
        avg_confidence,
        stop_event=stop_event,
        status_callback=status_callback,
        department_hint=department_hint,
    )
```

- [ ] **Step 4: `ocr_pipeline_structure.py` — thread the hint through `_run_pro_vision_fallback`**

Change the signature (line 169) from:

```python
def _run_pro_vision_fallback(image, api_key, data_store, stop_event, status_callback, stage, validation_report):
```

to:

```python
def _run_pro_vision_fallback(image, api_key, data_store, stop_event, status_callback, stage, validation_report, department_hint=None):
```

Change the engine call (lines 174-178) from:

```python
    result = pro_engine.extract_image_directly(
        image,
        stop_event=stop_event,
        status_callback=status_callback,
    )
```

to:

```python
    result = pro_engine.extract_image_directly(
        image,
        stop_event=stop_event,
        status_callback=status_callback,
        department_hint=department_hint,
    )
```

- [ ] **Step 5: Verify nothing broke (existing tests + import smoke)**

Run: `python -m pytest tests/ -v`
Expected: PASS (no regressions; new tests from Tasks 1-4 still pass)

Run: `python -c "import module_flash_ocr, module_pro_ocr, fallback_light_structurer, ocr_pipeline_structure; print('imports ok')"`
Expected: `imports ok`

- [ ] **Step 6: Commit**

```bash
git add module_flash_ocr.py module_pro_ocr.py fallback_light_structurer.py ocr_pipeline_structure.py
git commit -m "feat: pass department_hint into light + Pro Vision prompts"
```

---

### Task 6: Wire `dept_map`, override, and escalation gate into `run_pipeline`

**Files:**
- Modify: `ocr_pipeline_structure.py` (`run_pipeline`, lines 190-350)
- Test: `tests/test_run_pipeline_dept.py`

This task wires the already-tested helpers into the per-image loop. The unit test stubs the heavy engines and verifies the dept override + escalation decision; full OCR is verified manually.

- [ ] **Step 1: Add `dept_map` param**

Change line 190 from:

```python
def run_pipeline(input_dir: str, stop_event, api_key: str, signals) -> str:
```

to:

```python
def run_pipeline(input_dir: str, stop_event, api_key: str, signals, dept_map=None) -> str:
```

- [ ] **Step 2: Resolve dept per file**

After line 224 (`processed_ok = False`), insert:

```python
        dept = (dept_map or {}).get(filename)
        if dept_map is not None and not dept:
            _log(f"Bộ phận chưa gán cho {filename} — dùng suy luận tự động.")
```

- [ ] **Step 3: Apply override right after the JSON is built**

After line 262 (`)` closing `build_invoice_json(...)`), and before line 263 `json_rough = enrich_supplier(...)`, insert:

```python
            json_rough = _apply_department_override(json_rough, dept)
```

- [ ] **Step 4: Pass dept into the direct-vision fallback + re-apply override**

Change the direct-vision call (lines 277-285) from:

```python
                json_rough = _run_pro_vision_fallback(
                    image,
                    api_key,
                    app_data,
                    stop_event,
                    _log,
                    "direct_after_structure",
                    validation,
                )
```

to:

```python
                json_rough = _run_pro_vision_fallback(
                    image,
                    api_key,
                    app_data,
                    stop_event,
                    _log,
                    "direct_after_structure",
                    validation,
                    department_hint=dept,
                )
                json_rough = _apply_department_override(json_rough, dept)
```

- [ ] **Step 5: Pass dept into the light fallback + re-apply override**

Change the light-fallback call (lines 288-295) from:

```python
                json_rough = run_light_fallback(
                    normalized,
                    normalized.get("avg_confidence", 0.0),
                    api_key,
                    app_data,
                    stop_event=stop_event,
                    status_callback=_log,
                )
```

to:

```python
                json_rough = run_light_fallback(
                    normalized,
                    normalized.get("avg_confidence", 0.0),
                    api_key,
                    app_data,
                    stop_event=stop_event,
                    status_callback=_log,
                    department_hint=dept,
                )
                json_rough = _apply_department_override(json_rough, dept)
```

- [ ] **Step 6: Pass dept into the after-light vision fallback + re-apply override**

Change the after-light vision call (lines 313-321) from:

```python
                    json_rough = _run_pro_vision_fallback(
                        image,
                        api_key,
                        app_data,
                        stop_event,
                        _log,
                        "after_light_fallback",
                        light_validation,
                    )
```

to:

```python
                    json_rough = _run_pro_vision_fallback(
                        image,
                        api_key,
                        app_data,
                        stop_event,
                        _log,
                        "after_light_fallback",
                        light_validation,
                        department_hint=dept,
                    )
                    json_rough = _apply_department_override(json_rough, dept)
```

- [ ] **Step 7: Add the consolidated weak-signal escalation gate**

After the fallback `if/elif/else` block ends — i.e. after line 327 (`_log("Ket qua local du manh -> khong can fallback model nhe.")`) and its closing of the `else:` — insert this block BEFORE line 329 (`calc_engine = get_calculator(...)`):

```python
            already_pro = json_rough.get("_structure_pipeline", {}).get("pro_vision_fallback_used")
            val_now = json_rough.get("_structure_pipeline", {}).get("validation", validation)
            if not already_pro and _should_escalate_weak_result(json_rough, val_now):
                _log("Tin hieu yeu / chu viet tay -> nang cap Pro Vision.")
                json_rough = _run_pro_vision_fallback(
                    image,
                    api_key,
                    app_data,
                    stop_event,
                    _log,
                    "weak_signal_escalation",
                    val_now,
                    department_hint=dept,
                )
                json_rough = _apply_department_override(json_rough, dept)
```

- [ ] **Step 8: Write the failing test**

```python
# tests/test_run_pipeline_dept.py
import types
import ocr_pipeline_structure as ops


def test_apply_override_wins_over_ocr_department():
    j = {"transaction_info": {"department": "BAR"}}   # OCR-guessed
    ops._apply_department_override(j, "BEP")           # user tag
    assert j["transaction_info"]["department"] == "BEP"
    assert j["_department_source"] == "user_tag"


def test_escalation_gate_decision_matches_predicate():
    # garbled -> should escalate
    garbled = {
        "document_info": {"invoice_type": "VAT_INVOICE"},
        "transaction_info": {"invoice_number": "X", "invoice_date": "2026-01-01"},
        "items": [{"product_name": n} for n in ["cāB", "xutg", "B'd", "10Hinh"]],
        "totals": {},
    }
    assert ops._should_escalate_weak_result(garbled, {"confidence": 0.86}) is True

    clean = {
        "document_info": {"invoice_type": "VAT_INVOICE"},
        "transaction_info": {"invoice_number": "DO-1", "invoice_date": "2026-01-01"},
        "items": [{"product_name": "Ba rọi xông khói Tasany 3mm"}],
        "totals": {},
    }
    assert ops._should_escalate_weak_result(clean, {"confidence": 0.95}) is False


def test_run_pipeline_accepts_dept_map_kwarg():
    # signature smoke: dept_map is an accepted keyword with a default
    import inspect
    sig = inspect.signature(ops.run_pipeline)
    assert "dept_map" in sig.parameters
    assert sig.parameters["dept_map"].default is None
```

- [ ] **Step 9: Run tests**

Run: `python -m pytest tests/test_run_pipeline_dept.py tests/test_escalation_predicate.py tests/test_department_override.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add ocr_pipeline_structure.py tests/test_run_pipeline_dept.py
git commit -m "feat: thread user-tagged dept + weak-signal escalation into run_pipeline"
```

---

### Task 7: `DepartmentTaggingDialog` Qt view

**Files:**
- Modify: `department_tagging_dialog.py` (append the Qt dialog class)

No automated test (needs a display). Manual checklist in Step 3.

- [ ] **Step 1: Append the dialog class**

Add to the end of `department_tagging_dialog.py`:

```python
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QWidget, QMessageBox, QSizePolicy,
)

from post_process_dialog import _load_invoice_pixmap  # reuse Pillow-fallback loader

_DEPT_HOTKEYS = {
    Qt.Key_1: "BEP", Qt.Key_2: "BAR", Qt.Key_3: "BANH", Qt.Key_4: "RANG",
}


class DepartmentTaggingDialog(QDialog):
    """Tag each invoice image to a department before scanning.

    image_paths: list of absolute paths (order is cosmetic; the returned map is
    keyed by basename to line up with how the pipeline iterates os.listdir).
    store_name: optional label shown at top (forward-compat seam for multi-store).
    """

    def __init__(self, image_paths, store_name="Lighthouse", parent=None):
        super().__init__(parent)
        self._paths_by_name = {os.path.basename(p): p for p in image_paths}
        self.state = TaggingState([os.path.basename(p) for p in image_paths])
        self.setWindowTitle("Gán bộ phận cho hoá đơn")
        self.resize(1100, 760)
        self._build_ui(store_name)
        self._refresh()

    # ---- UI construction ----
    def _build_ui(self, store_name):
        root = QHBoxLayout(self)

        # Left ~35%
        left = QVBoxLayout()
        self.lbl_store = QLabel(f"Cửa hàng: {store_name}")
        self.lbl_store.setStyleSheet("font-weight:600;")
        left.addWidget(self.lbl_store)

        self.lbl_progress = QLabel()
        left.addWidget(self.lbl_progress)

        self._dept_buttons = {}
        for key, dept in _DEPT_HOTKEYS.items():
            label = key - Qt.Key_0
            btn = QPushButton(f"[{label}]  {dept}")
            btn.setMinimumHeight(48)
            btn.clicked.connect(lambda _=False, d=dept: self._assign(d))
            left.addWidget(btn)
            self._dept_buttons[dept] = btn

        self.list_files = QListWidget()
        self.list_files.currentRowChanged.connect(self._on_row_changed)
        left.addWidget(self.list_files, 1)

        self.btn_start = QPushButton("✅ Bắt đầu xử lý")
        self.btn_start.clicked.connect(self._on_start)
        left.addWidget(self.btn_start)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(360)
        root.addWidget(left_w)

        # Right ~65%
        right = QVBoxLayout()
        self.lbl_header = QLabel()
        self.lbl_header.setStyleSheet("font-weight:600;")
        right.addWidget(self.lbl_header)
        self.lbl_image = QLabel("(không có ảnh)")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        right.addWidget(self.lbl_image, 1)
        root.addLayout(right, 1)

        # Populate the file list once
        for name in self.state.filenames:
            self.list_files.addItem(QListWidgetItem(name))

    # ---- actions ----
    def _assign(self, dept):
        self.state.assign(dept)
        self._sync_list_selection()
        self._refresh()

    def _on_row_changed(self, row):
        if row >= 0 and row != self.state.current_index:
            self.state.goto(row)
            self._refresh()

    def _sync_list_selection(self):
        self.list_files.blockSignals(True)
        self.list_files.setCurrentRow(self.state.current_index)
        self.list_files.blockSignals(False)

    def _on_start(self):
        if self.state.is_complete():
            self.accept()

    # ---- rendering ----
    def _refresh(self):
        self._sync_list_selection()
        total = self.state.total
        idx = self.state.current_index
        name = self.state.current_filename() or ""
        self.lbl_header.setText(f"Ảnh {idx + 1} / {total} — {name}")
        self.lbl_progress.setText(
            f"Đã gán: {self.state.assigned_count()} / {total}"
        )
        # badge each list row with its dept
        for i, fn in enumerate(self.state.filenames):
            dept = self.state.department_of(fn)
            self.list_files.item(i).setText(f"{fn}   [{dept or '—'}]")
        # highlight the current image's assigned dept button
        cur_dept = self.state.department_of(name)
        for dept, btn in self._dept_buttons.items():
            btn.setStyleSheet(
                "background:#2f6fb0; color:white; font-weight:700;"
                if dept == cur_dept else ""
            )
        self.btn_start.setEnabled(self.state.is_complete())
        self._render_image(name)

    def _render_image(self, name):
        path = self._paths_by_name.get(name)
        if not path or not os.path.exists(path):
            self.lbl_image.setText("Không tải được ảnh")
            self.lbl_image.setPixmap(self.lbl_image.pixmap() or self._empty_pixmap())
            return
        pix = _load_invoice_pixmap(path)
        if pix.isNull():
            self.lbl_image.setText("Không tải được ảnh")
            return
        target_w = max(200, self.lbl_image.width())
        self.lbl_image.setPixmap(pix.scaledToWidth(target_w, Qt.SmoothTransformation))

    def _empty_pixmap(self):
        from PyQt5.QtGui import QPixmap
        return QPixmap()

    def showEvent(self, event):
        super().showEvent(event)
        self._render_image(self.state.current_filename() or "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_image(self.state.current_filename() or "")

    # ---- keys ----
    def keyPressEvent(self, event):
        key = event.key()
        if key in _DEPT_HOTKEYS:
            self._assign(_DEPT_HOTKEYS[key])
            return
        if key in (Qt.Key_Backspace, Qt.Key_Left):
            self.state.back(); self._refresh(); return
        if key == Qt.Key_Right:
            self.state.forward(); self._refresh(); return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._on_start(); return
        if key == Qt.Key_Escape:
            self._confirm_cancel(); return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Treat the window [X] like Esc: confirm, then abort the scan.
        event.ignore()
        self._confirm_cancel()

    def _confirm_cancel(self):
        resp = QMessageBox.question(
            self, "Hủy phiên scan",
            "Hủy toàn bộ phiên scan? Chưa gán đủ bộ phận nên sẽ không xử lý ảnh nào.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.reject()

    def get_department_map(self):
        return self.state.get_department_map()
```

- [ ] **Step 2: Import smoke test**

Run: `python -c "import department_tagging_dialog; print('ok')"`
Expected: `ok` (imports without error; no display needed for import)

- [ ] **Step 3: Manual checklist (run the app, press Scan with a few test images)**

  - Dialog opens with image on the right, 4 dept buttons + file list on the left.
  - Keys `1/2/3/4` tag the current image and auto-advance to the next unassigned.
  - Current image's assigned dept button is highlighted.
  - `←`/`Backspace` goes to previous; clicking a file-list row jumps to it.
  - "Bắt đầu xử lý" is disabled until every image is tagged; `Enter` then proceeds.
  - `Esc` / window-close asks to confirm; confirming aborts (no scan).
  - A corrupt/unreadable image shows "Không tải được ảnh" but tagging still works.

- [ ] **Step 4: Commit**

```bash
git add department_tagging_dialog.py
git commit -m "feat: DepartmentTaggingDialog Qt view over TaggingState"
```

---

### Task 8: Wire the dialog into the Scan flow

**Files:**
- Modify: `main_app_qt.py` (`OCRWorker.__init__` ~375, `_run_pipeline` ~411, `_start_scan` ~1520)
- Modify: `ocr_pipeline.py` (legacy `run_pipeline` signature — accept `dept_map=None`)

- [ ] **Step 1: `OCRWorker` accepts and forwards `dept_map`**

Change `OCRWorker.__init__` (lines 375-381) from:

```python
    def __init__(self, input_dir: str, stop_event: threading.Event,
                 api_key: str, signals: WorkerSignals):
        super().__init__()
        self.input_dir  = input_dir
        self.stop_event = stop_event
        self.api_key    = api_key
        self.s          = signals
```

to:

```python
    def __init__(self, input_dir: str, stop_event: threading.Event,
                 api_key: str, signals: WorkerSignals, dept_map: dict = None):
        super().__init__()
        self.input_dir  = input_dir
        self.stop_event = stop_event
        self.api_key    = api_key
        self.s          = signals
        self.dept_map   = dept_map
```

Change the structure-pipeline call (lines 411-417) from:

```python
        from ocr_pipeline_structure import run_pipeline as run_structure_pipeline
        self._output_path = run_structure_pipeline(
            self.input_dir,
            self.stop_event,
            self.api_key,
            self.s,
        )
        return
```

to:

```python
        from ocr_pipeline_structure import run_pipeline as run_structure_pipeline
        self._output_path = run_structure_pipeline(
            self.input_dir,
            self.stop_event,
            self.api_key,
            self.s,
            dept_map=self.dept_map,
        )
        return
```

Change the legacy-pipeline call (lines 402-408) from:

```python
            from ocr_pipeline import run_pipeline as run_legacy_pipeline
            self._output_path = run_legacy_pipeline(
                self.input_dir,
                self.stop_event,
                self.api_key,
                self.s,
            )
            return
```

to:

```python
            from ocr_pipeline import run_pipeline as run_legacy_pipeline
            self._output_path = run_legacy_pipeline(
                self.input_dir,
                self.stop_event,
                self.api_key,
                self.s,
                dept_map=self.dept_map,
            )
            return
```

- [ ] **Step 2: Legacy pipeline accepts the kwarg (no behavior change)**

In `ocr_pipeline.py`, find its `def run_pipeline(input_dir...` signature and append `, dept_map=None` so the call above does not raise. (Legacy only needs to accept it; metadata override there is optional and out of scope for this task.)

Run to confirm the legacy signature was updated:
Run: `python -c "import inspect, ocr_pipeline; print('dept_map' in inspect.signature(ocr_pipeline.run_pipeline).parameters)"`
Expected: `True`

- [ ] **Step 3: `_start_scan` opens the dialog before starting the worker**

In `main_app_qt.py`, locate the block (lines 1523-1527):

```python
        input_dir = self.entry_folder.text().strip()
        if not input_dir or not os.path.isdir(input_dir):
            QMessageBox.warning(self, "Lỗi đường dẫn",
                "Thư mục đầu vào không hợp lệ. Vui lòng chọn lại!")
            return
```

Insert immediately AFTER it:

```python
        valid_ext = ('.png', '.jpg', '.jpeg')
        image_files = sorted(
            f for f in os.listdir(input_dir) if f.lower().endswith(valid_ext)
        )
        if not image_files:
            QMessageBox.warning(self, "Không có ảnh",
                "Thư mục đầu vào không có ảnh (.png/.jpg/.jpeg).")
            return

        from department_tagging_dialog import DepartmentTaggingDialog
        image_paths = [os.path.join(input_dir, f) for f in image_files]
        tag_dlg = DepartmentTaggingDialog(image_paths, parent=self)
        if tag_dlg.exec_() != QDialog.Accepted:
            self._append_log("🛑 Đã hủy phiên scan — chưa gán bộ phận.")
            return
        dept_map = tag_dlg.get_department_map()
```

Then change the worker construction (lines 1551-1556) from:

```python
        self._worker = OCRWorker(
            input_dir=input_dir,
            stop_event=self._stop_event,
            api_key=GEMINI_API_KEY,
            signals=signals
        )
```

to:

```python
        self._worker = OCRWorker(
            input_dir=input_dir,
            stop_event=self._stop_event,
            api_key=GEMINI_API_KEY,
            signals=signals,
            dept_map=dept_map,
        )
```

- [ ] **Step 4: Ensure `QDialog` is imported in `main_app_qt.py`**

Confirm `QDialog` is among the `from PyQt5.QtWidgets import (...)` names near the top of `main_app_qt.py`. If not present, add `QDialog` to that import list.

Run: `python -c "import main_app_qt; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Run the full test suite (no regressions)**

Run: `python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add main_app_qt.py ocr_pipeline.py
git commit -m "feat: open department tagging dialog before scan; pass dept_map to worker"
```

---

### Task 9: Surface dept source in trace + changelog

**Files:**
- Modify: `pipeline_trace.py` (`route_detail` / `route_label` — append "(gán tay)" when `_department_source == 'user_tag'`)
- Modify: `CLAUDE.md` (changelog entry)

- [ ] **Step 1: Read the current `route_detail` builder**

Run: `python -c "import pipeline_trace, inspect; print(inspect.getsource(pipeline_trace.route_detail))"`
Expected: prints the function source (use it to place the edit precisely).

- [ ] **Step 2: Append department-source note in `route_detail`**

In `pipeline_trace.py`, inside `route_detail(invoice_json)`, where the supplier-resolution / department info is assembled into the one-liner, add a department segment. Insert near where the detail string parts are collected:

```python
    dept = str((invoice_json.get("transaction_info") or {}).get("department") or "").strip()
    if dept:
        src = invoice_json.get("_department_source")
        parts.append(f"Bộ phận: {dept}" + (" (gán tay)" if src == "user_tag" else ""))
```

(Use the function's existing `parts`/list-builder variable name as seen in Step 1; if the function concatenates a string instead of a list, append the same `"Bộ phận: ... (gán tay)"` fragment to that string with the same separator the function already uses.)

- [ ] **Step 3: Smoke test the trace helper**

Run:
```bash
python -c "import pipeline_trace; d=pipeline_trace.route_detail({'transaction_info':{'department':'BEP'},'_department_source':'user_tag','_structure_pipeline':{}}); print(d)"
```
Expected: output contains `Bộ phận: BEP (gán tay)`

- [ ] **Step 4: Add the CLAUDE.md changelog entry**

In `CLAUDE.md`, under the `## Changelog` → `### Unreleased` area, add a new bullet block:

```markdown
### Unreleased - Pre-Scan Department Tagging + Wider Pro Vision Escalation
- **Mandatory pre-scan department tagging dialog** (`department_tagging_dialog.py`): pressing Scan now opens `DepartmentTaggingDialog` (thin Qt view over a headless `TaggingState`) that tags every invoice image to one of BEP/BAR/BANH/RANG via hotkeys `1–4`, with a fit-to-width image preview, a clickable file list for corrections, and auto-advance. Cancelling/closing aborts the whole scan (no image processed). The `{filename → dept}` map flows through `OCRWorker(dept_map=…)` into `run_pipeline`. New shared `departments.py` (`VALID_DEPARTMENTS`, `department_prompt_line`).
- **User-tagged department is authoritative**: `ocr_pipeline_structure._apply_department_override` stamps `transaction_info.department` (+ `_department_source = "user_tag"`) after JSON build and after every fallback, so the Excel mapper hard-sets BỘ PHẬN + KHO from the user's choice instead of OCR guesses. The department is also injected into the light-fallback and Pro Vision prompts (`department_prompt_line`) to improve handwriting legibility within that department's product set.
- **Wider Pro Vision escalation**: new `_should_escalate_weak_result` escalates weak/handwritten results to Pro Vision when item names look garbled, a total-mismatch warning exists, the invoice looks handwritten with confidence < 0.90, or confidence < 0.80 for any type — instead of leaving them on the text-only light fallback. Thresholds are module constants (`WEAK_HANDWRITTEN_CONF`, `WEAK_ANY_CONF`, `GARBLED_NAME_RATIO`). The unreliable LLM `invoice_type` label is no longer the sole signal.
- **Trace**: `pipeline_trace.route_detail` shows `Bộ phận: BEP (gán tay)` when the department was user-tagged.
```

- [ ] **Step 5: Run the full suite one more time**

Run: `python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline_trace.py CLAUDE.md
git commit -m "feat: show user-tagged dept in trace; changelog for dept tagging + escalation"
```

---

## Self-Review (filled in by plan author)

**Spec coverage:**
- Dialog (4 depts, mandatory, hotkeys, preview, auto-advance, clickable list, cancel=abort) → Tasks 2, 7, 8. ✓
- Store forward-compat seam → Task 7 (`store_name` label / map keyed by filename). ✓
- Authoritative dept override + KHO/F-column (already wired in mapper) → Tasks 4, 6. ✓
- Dept into light + Pro prompts → Tasks 1, 5, 6. ✓
- Weak-signal escalation (garbled / total mismatch / handwritten+conf / any<0.80) → Tasks 3, 6. ✓
- Error logging (skip/stop reasons, missing-tag fallback log) → Task 6 Step 2; existing per-image try/except already logs full multi-line reasons. ✓
- Backward compat (`dept_map=None`) → Tasks 6, 8 (defaults + signature smoke test). ✓
- Tests (tagging state, escalation predicate, override) → Tasks 2, 3, 4, 6. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type/name consistency:** `TaggingState`, `get_department_map()`, `_apply_department_override`, `_should_escalate_weak_result`, `department_prompt_line`, `VALID_DEPARTMENTS`, `dept_map` used consistently across tasks. ✓

**Note for executor:** line numbers reference the file state at plan-writing time; if a prior task shifted lines, match on the quoted code text rather than the line number.
