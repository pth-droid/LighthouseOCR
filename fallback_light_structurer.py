import json


def should_use_light_fallback(validation_report):
    return not bool(validation_report.get("can_use_local_result"))


def build_light_fallback_text(normalized_structure):
    compact = {
        "raw_text": normalized_structure.get("raw_text") or "",
        "regions": normalized_structure.get("regions") or [],
        "tokens": normalized_structure.get("tokens") or [],
        "tables": normalized_structure.get("tables") or [],
    }
    return (
        "RAW_TEXT:\n"
        f"{compact['raw_text']}\n\n"
        "REGIONS:\n"
        f"{json.dumps(compact['regions'], ensure_ascii=False)}\n\n"
        "TOKENS:\n"
        f"{json.dumps(compact['tokens'], ensure_ascii=False)}\n\n"
        "TABLES:\n"
        f"{json.dumps(compact['tables'], ensure_ascii=False)}"
    )


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
    result.setdefault("_structure_pipeline", {})
    result["_structure_pipeline"]["fallback_used"] = True
    return result
