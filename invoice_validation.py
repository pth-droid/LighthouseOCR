def _has_value(value):
    return value not in (None, "", [], {})


def _has_any_pricing(item):
    return _has_value(item.get("total_price")) or _has_value(item.get("unit_price"))


def validate_invoice_json(invoice_json):
    missing = []
    if not _has_value((invoice_json.get("supplier_info") or {}).get("supplier_name_code")):
        missing.append("supplier_name_code")
    if not invoice_json.get("items"):
        missing.append("items")
    if not _has_value((invoice_json.get("totals") or {}).get("total_amount")):
        missing.append("total_amount")

    priced_items = [item for item in invoice_json.get("items", []) if _has_any_pricing(item)]
    if invoice_json.get("items") and not priced_items:
        missing.append("item_pricing")

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
