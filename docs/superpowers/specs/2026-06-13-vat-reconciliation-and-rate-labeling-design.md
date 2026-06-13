# VAT Reconciliation + Rate Labeling — Design Spec

- **Date**: 2026-06-13
- **Status**: Approved (verbal), proceeding to implementation
- **Scope**: 2 high-priority fixes surfaced by the DONE-folder comparison (LLM chat vs LH OCR improved)

## Problem

Comparison of 7 invoices processed two ways exposed two defects in the default
PP-StructureV3 pipeline, both on the **light/Flash fallback** branch:

1. **VAT under-read on multi-column / multi-rate invoices.** Invoice `r23`
   (Bách Phúc Phương, `20260528_145917`) has two separate VAT columns (`VAT 8%`
   and `VAT 5%`). The text-only light fallback captured VAT for only **1 of 4**
   line items, mislabeled its rate, and reported a grand total of **1,379,700**
   — the printed total is **1,398,501** (verified against the source image).
   Missing **18,801đ** of VAT. The existing `FIX-4` reconciliation
   (`module_calculator._normalize_pricing_basis`) did not catch it because its
   5% divergence threshold is looser than the VAT-sized error, and the
   escalation gate that consumes `total_discrepancy_warning` runs *before* the
   calculator that sets it (see Architecture note).

2. **VAT rate label trusts the LLM guess over the math.** The stored `vat_rate`
   comes straight from the LLM's `raw_vat_rate` string. On `r10` (`20260522_125908`)
   the calculator stored **8%** for lines whose own VAT amounts imply **5%**
   (48,750 / 975,000 = 5.0%). The dong amounts matched the reference, but the
   per-line rate label is wrong — which corrupts VAT declarations.

### Architecture note (root cause of #1 going undetected)

In `ocr_pipeline_structure.run_pipeline`, the weak-result escalation gate
`_should_escalate_weak_result` (which calls `_has_total_mismatch`) runs at the
pre-calc stage. But `total_discrepancy_warning` is only set **inside**
`module_calculator._normalize_pricing_basis`, which runs **after** the gate.
So the total-mismatch branch of the gate is effectively dead on the structure /
light-fallback path. This must be fixed by adding a **post-calc** escalation
check.

## Goals / Non-goals

- **Goal**: Detect VAT/total inconsistency deterministically and locally; when
  detected, escalate the invoice to Pro Vision once and recompute.
- **Goal**: Store the VAT rate the arithmetic implies, not the LLM's guess.
- **Non-goal**: Recompute per-line VAT locally when rates are missing (r23 only
  read 1 of 4 rates — not reconstructable; Vision is the answer).
- **Non-goal**: Touch the other branches of `_should_escalate_weak_result`
  (garbled names, handwritten, low confidence) or the legacy pipeline.

## Design

### Fix #2 — VAT rate from arithmetic (pure, in `module_calculator.py`)

New module-level constants + pure helper (unit-testable in isolation):

```python
STANDARD_VAT_RATES = (0.0, 5.0, 8.0, 10.0)
VAT_SNAP_TOLERANCE = 0.5   # percentage points

def _snap_vat_rate(rate: float) -> float | None:
    """Return the standard VAT rate within tolerance, else None."""
```

Inside the per-line loop of `_normalize_pricing_basis`, after `line_vat_amount`
and `discounted_total` are known:

- `derived = line_vat_amount / discounted_total * 100` when both `> 0`.
- If `derived` snaps to a standard rate → **store the snapped standard rate** in
  `vat_rate` (overrides the LLM `raw_vat_rate` label). → r10: store **5%**.
- If `derived` does **not** snap (e.g. 52,080 / 908,020 = 5.74%) → the VAT amount
  is suspect → mark the line `_vat_inconsistent = True` and store
  `round(derived, 2)` so the real figure is visible. → r23 item 1 flagged.
- Lines with no VAT (amount 0, rate null) keep `vat_rate = None` (unchanged).
  → delivery notes r3 (TM/CK, VAT 0) are untouched.

The line dict gains an internal `_vat_inconsistent` boolean (not part of the
public schema; consumed only by reconciliation).

### Fix #1a — VAT-aware total reconciliation (in `module_calculator.py`)

Replace the inline `FIX-4` block with a helper:

```python
def _reconcile_totals(grand_total, declared_total, has_vat, vat_inconsistent_count) -> str | None
```

Sets `total_discrepancy_warning` (reuses the existing key) when **either**:

- **Signal 2 (primary, robust):** `vat_inconsistent_count > 0` — a line has a
  positive VAT amount whose derived rate is non-standard. Catches r23 regardless
  of what total the fallback reported.
- **Signal 1 (total divergence):** `declared_total > 0 and grand_total > 0` and
  `divergence > tol and abs_diff > 5000`, where `tol = 0.01` (1%) for
  VAT-bearing invoices (`has_vat`) and `tol = 0.05` (5%) otherwise. The 5%
  branch preserves the legacy FIX-4 behavior for handwritten / no-VAT invoices.

All warning strings keep the substring `CẢNH BÁO` (consumed by
`_has_total_mismatch` truthiness check and asserted by existing tests).

Threshold rationale: clean printed invoices reconcile to < 0.1%; a single missed
VAT line on a VAT invoice is ~1–8% of total. Seller hand-rounding on no-VAT
slips (the legacy raw3 fixture: 0.52%, 1,000đ) stays under both the 5% and the
5,000đ absolute floor → no false warning.

### Fix #1b — Post-calc escalation wiring (in `ocr_pipeline_structure.py`)

After `calc_engine.run_calculation(...)`, before the reviewable-data check:

```python
already_pro = json_rough.get("_structure_pipeline", {}).get("pro_vision_fallback_used")
if not already_pro and _has_total_mismatch(invoice_json):
    _log("Tong/VAT khong khop -> nang cap Pro Vision doc lai.")
    json_rough = _run_pro_vision_fallback(
        image, api_key, app_data, stop_event, _log,
        "total_reconciliation", val_now, department_hint=dept,
    )
    json_rough = _apply_department_override(json_rough, dept)
    invoice_json = calc_engine.run_calculation(json_rough, stop_event=stop_event, status_callback=_log)
```

- Runs at most once (`already_pro` guard prevents loops and skips invoices that
  already used Pro Vision, e.g. the handwritten r12/r10_145741).
- If Vision still doesn't reconcile, the warning persists → review UI highlights
  it for manual correction (no infinite loop).
- `_run_pro_vision_fallback` stamps `_structure_pipeline`, carried into
  `invoice_json` by the existing merge at the post-processing step, so
  `pipeline_trace.build_route` reflects the `total_reconciliation` stage.

## Components / boundaries

| Unit | File | Responsibility | Pure? |
|---|---|---|---|
| `_snap_vat_rate` | module_calculator.py | rate → standard rate or None | yes |
| per-line VAT resolution | module_calculator.py (`_normalize_pricing_basis`) | derive+snap rate, flag inconsistency | yes |
| `_reconcile_totals` | module_calculator.py | produce warning from signals | yes |
| post-calc escalation | ocr_pipeline_structure.py (`run_pipeline`) | escalate once + recompute | no (I/O) |

## Expected behavior on the 7-invoice corpus

| Invoice | Today | After |
|---|---|---|
| r10_125908 (BPHUC, printed) | VAT labeled 8% (math 5%) | relabeled **5%/8%**; total unchanged; no escalation |
| r23_145917 (BPHUC, printed) | total 1,379,700 (−18,801) | item1 flagged `_vat_inconsistent` → warning → **escalate Pro Vision** → recompute → 1,398,501 |
| r3_130157 / r3_145614 (SANGNGOC, TM/CK) | VAT 0 | unchanged (no VAT, reconciles) — no escalation |
| r4_151830 (MOONMILK, printed) | VAT 8% all lines | rates snap to 8%; reconciles — no escalation |
| r12 / r10_145741 (handwritten) | already Pro Vision | unchanged (`already_pro` guard) |

## Test plan (TDD, unittest)

New `tests/test_vat_reconciliation.py`:

- `_snap_vat_rate`: snaps 5.0/8.0/10.0/0.0 within ±0.5pp; returns None for 5.74,
  7.3, etc.
- Relabel: r10_125908-shaped fixture (amount implies 5%, label "8%") → stored
  `vat_rate == 5.0`, no `total_discrepancy_warning`.
- Inconsistency: r23-shaped fixture (item1 amount 52,080 on base 908,020, other
  lines no VAT) → `total_discrepancy_warning` set (contains CẢNH BÁO).
- No false positive: TM/CK delivery note (all VAT 0) → no warning.
- Total divergence: VAT invoice with declared total off by >1% & >5,000đ → warning;
  off by <1% → none.

Regression: `tests/test_all_fixes.py` FIX-4 (raw2 26.7% no-VAT → warn; raw3
0.52% no-VAT → no warn) must stay green (no-VAT path keeps 5% + 5,000đ floor).

Wiring (`tests/test_escalation_predicate.py` or a new pipeline test):
monkeypatch `_run_pro_vision_fallback` + `run_calculation` to assert the
post-calc block escalates exactly once when `_has_total_mismatch` is true and
`already_pro` is false, and does **not** escalate when `already_pro` is true.

## Risks

- `test_all_fixes.py` could break if the no-VAT 5% path is altered — mitigated by
  keeping that path's threshold at 5% and gating the 1% only behind `has_vat`.
- Extra Pro Vision call cost — bounded to invoices that genuinely fail
  reconciliation; the clean printed invoices in the corpus do not trigger it.
- A misread VAT amount that coincidentally yields a near-standard rate would not
  be flagged by Signal 2 — Signal 1 (total divergence) and the existing
  weak-signal gate remain as backstops.
