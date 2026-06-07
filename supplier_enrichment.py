import copy
import re
import unicodedata


UNKNOWN_SUPPLIER_CODES = {"", "null", "none", "mua le", "mua lẻ", "n/a"}


def _clean(value):
    text = str(value or "").strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_known_supplier(code):
    return _clean(code) not in UNKNOWN_SUPPLIER_CODES


def _looks_like_salesperson_supplier(raw_name):
    raw_clean = _clean(raw_name)
    if not raw_clean:
        return False
    company_markers = (
        "cong ty",
        "tnhh",
        "co phan",
        "chi nhanh",
        "doanh nghiep",
        "cua hang",
        "hop tac xa",
    )
    if any(marker in raw_clean for marker in company_markers):
        return False
    salesperson_markers = ("nvbh", "hrc", "ten nv", "nhan vien", "sales", "giao nhan")
    return any(marker in raw_clean for marker in salesperson_markers)


def _split_product_samples(text):
    samples = []
    for token in re.split(r"[,;/|]+", str(text or "")):
        cleaned = token.strip()
        if cleaned:
            samples.append(cleaned)
    return samples


def _parse_supplier_catalog(data_store):
    suppliers = {}
    for code, name in getattr(data_store, "suppliers_dict", {}).items():
        suppliers[str(code).strip()] = {"name": str(name).strip(), "products": []}

    context = str(getattr(data_store, "suppliers_context_str", "") or "")
    for part in context.split("|"):
        if "=" not in part:
            continue
        code, rest = part.split("=", 1)
        code = code.strip()
        name = rest.split("(", 1)[0].strip()
        products = []
        match = re.search(r"\((?:[^:]+):\s*([^)]+)\)", rest)
        if match:
            products = _split_product_samples(match.group(1))
        entry = suppliers.setdefault(code, {"name": name, "products": []})
        if name:
            entry["name"] = name
        if products:
            entry["products"] = products
    return suppliers


def _invoice_item_names(invoice_json):
    names = []
    for item in invoice_json.get("items", []) or []:
        name = str((item or {}).get("product_name") or "").strip()
        if name:
            names.append(name)
    return names


def _score_supplier_from_items(item_names, supplier_entry):
    evidence = []
    clean_items = [(_clean(name), name) for name in item_names]
    for sample in supplier_entry.get("products", []) or []:
        clean_sample = _clean(sample)
        if not clean_sample:
            continue
        for clean_item, original_item in clean_items:
            if not clean_item:
                continue
            if clean_sample in clean_item or clean_item in clean_sample:
                if original_item not in evidence:
                    evidence.append(original_item)
                break
    return len(evidence), evidence


def _infer_supplier_from_items(invoice_json, data_store):
    item_names = _invoice_item_names(invoice_json)
    if len(item_names) < 2:
        return None

    scored = []
    for code, entry in _parse_supplier_catalog(data_store).items():
        score, evidence = _score_supplier_from_items(item_names, entry)
        if score:
            scored.append((score, code, entry, evidence))

    if not scored:
        return None

    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best_code, best_entry, best_evidence = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0

    if best_score < 2 or best_score <= second_score:
        return None

    confidence = min(0.95, 0.65 + best_score * 0.10 + (best_score - second_score) * 0.05)
    return {
        "code": best_code,
        "name": best_entry.get("name") or best_code,
        "confidence": round(confidence, 3),
        "evidence": best_evidence,
    }


def _set_resolution(invoice_json, source, confidence, evidence=None):
    invoice_json["_supplier_resolution"] = {
        "source": source,
        "confidence": float(round(confidence, 3)),
        "evidence": evidence or [],
    }


def enrich_supplier(invoice_json, data_store):
    enriched = copy.deepcopy(invoice_json)
    supplier = enriched.setdefault("supplier_info", {})
    code = supplier.get("supplier_name_code")

    if _is_known_supplier(code) and not _looks_like_salesperson_supplier(supplier.get("supplier_name_raw")):
        if not supplier.get("supplier_name_raw"):
            supplier["supplier_name_raw"] = getattr(data_store, "suppliers_dict", {}).get(code)
        _set_resolution(enriched, "ocr_header", 0.95)
        return enriched

    if _looks_like_salesperson_supplier(supplier.get("supplier_name_raw")):
        supplier["supplier_name_code"] = None
        supplier["supplier_name_raw"] = None

    inferred = _infer_supplier_from_items(enriched, data_store)
    if inferred:
        supplier["supplier_name_code"] = inferred["code"]
        supplier["supplier_name_raw"] = inferred["name"]
        _set_resolution(
            enriched,
            "item_inference",
            inferred["confidence"],
            inferred["evidence"],
        )
        return enriched

    supplier.setdefault("supplier_name_code", None)
    supplier.setdefault("supplier_name_raw", None)
    _set_resolution(enriched, "unknown", 0.0)
    return enriched
