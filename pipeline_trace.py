"""
pipeline_trace.py

Builds a compact, human-readable "processing route" for a single invoice — which
actual pipeline path (engine + fallbacks) produced the result. Derived from the
metadata the pipelines already record (`_structure_pipeline`, `_supplier_resolution`,
`_local_evidence_rescue`).

The pipelines stamp the result of :func:`build_route` into the saved JSON under
``_processing_route`` so the route is persisted; the browsers display its ``label``.
"""


def infer_mode(invoice_json) -> str:
    """Best-effort pipeline mode for JSON saved before ``_processing_route`` existed."""
    sp = (invoice_json or {}).get("_structure_pipeline") or {}
    if sp.get("engine_primary") or sp.get("legacy_reason"):
        return "legacy_hybrid"
    return "structure_default"


def build_route(invoice_json, mode) -> dict:
    """
    Return a route summary: ``{mode, engine, final_stage, steps, supplier_source, label}``.

    ``steps`` is an ordered list of the stages actually taken; ``label`` joins them
    into a one-line string (e.g. ``"PP-StructureV3 local → Light fallback → Pro Vision"``).
    """
    invoice_json = invoice_json or {}
    sp = invoice_json.get("_structure_pipeline") or {}
    supplier = invoice_json.get("_supplier_resolution") or {}
    rescue = invoice_json.get("_local_evidence_rescue") or {}

    steps: list[str] = []

    if mode == "legacy_hybrid":
        engine = "Legacy Hybrid"
        primary = sp.get("engine_primary")
        steps.append("PaddleOCR (text)")
        if primary == "flash_structurer":
            steps.append("Flash Structurer")
        if sp.get("pro_vision_fallback_used"):
            reason = sp.get("legacy_reason")
            steps.append("Pro Vision" + (f" ({reason})" if reason else ""))
            final_stage = "legacy_pro_vision"
        elif primary == "pro_vision_direct":
            steps.append("Pro Vision")
            final_stage = "legacy_pro_vision"
        else:
            final_stage = "legacy_flash"
    else:
        mode = "structure_default"
        engine = "PP-StructureV3"
        steps.append("PP-StructureV3 local")
        if rescue:
            steps.append("Local evidence rescue")
        if sp.get("light_fallback_used"):
            steps.append("Light fallback")
        if sp.get("pro_vision_fallback_used"):
            stage = sp.get("fallback_stage")
            steps.append("Pro Vision" + (f" ({stage})" if stage else ""))
            final_stage = "pro_vision"
        elif sp.get("light_fallback_used"):
            final_stage = "light_fallback"
        else:
            final_stage = "local_structure"

    return {
        "mode": mode,
        "engine": engine,
        "final_stage": final_stage,
        "steps": steps,
        "supplier_source": supplier.get("source"),
        "label": " → ".join(steps) if steps else engine,
    }


def route_label(invoice_json) -> str:
    """One-line route label: stored ``_processing_route.label`` or freshly built."""
    stored = (invoice_json or {}).get("_processing_route") or {}
    if stored.get("label"):
        return stored["label"]
    return build_route(invoice_json, infer_mode(invoice_json))["label"]


def get_route(invoice_json) -> dict:
    """Return the stored route dict if complete, else build it fresh."""
    invoice_json = invoice_json or {}
    stored = invoice_json.get("_processing_route") or {}
    if stored.get("engine"):
        return stored
    return build_route(invoice_json, infer_mode(invoice_json))


_SUPPLIER_SRC_VI = {
    "read": "đọc trực tiếp",
    "direct": "đọc trực tiếp",
    "inferred": "suy luận từ sản phẩm",
    "unknown": "chưa xác định",
}


def route_detail(invoice_json) -> str:
    """
    Information-dense one-liner for the status bar: engine, full route, supplier
    resolution source, confidence, missing required fields and warning count.
    """
    invoice_json = invoice_json or {}
    route = get_route(invoice_json)
    parts = [f"⚙️ {route.get('engine', '?')}", f"Lộ trình: {route.get('label') or '—'}"]

    src = route.get("supplier_source")
    if src:
        parts.append(f"NCC: {_SUPPLIER_SRC_VI.get(src, src)}")

    dept = str((invoice_json.get("transaction_info") or {}).get("department") or "").strip()
    if dept:
        dsrc = invoice_json.get("_department_source")
        parts.append("Bộ phận: " + dept + (" (gán tay)" if dsrc == "user_tag" else ""))

    sp = invoice_json.get("_structure_pipeline") or {}
    validation = sp.get("validation") or {}
    conf = validation.get("confidence")
    if conf is None:
        conf = (invoice_json.get("document_info") or {}).get("confidence_score")
    try:
        parts.append(f"Tin cậy: {float(conf):.0%}")
    except (TypeError, ValueError):
        pass

    missing = validation.get("missing_required_fields") or []
    if missing:
        parts.append("Thiếu: " + ", ".join(str(m) for m in missing))

    warnings = sp.get("warnings") or []
    if warnings:
        parts.append(f"Cảnh báo: {len(warnings)}")

    return "    •    ".join(parts)
