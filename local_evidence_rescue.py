import copy
import os
import re
import tempfile
import unicodedata


MIN_SUPPLIER_RESCUE_CONFIDENCE = 0.85

COMPANY_MARKERS = (
    "cong ty",
    "tnhh",
    "co phan",
    "chi nhanh",
    "doanh nghiep",
    "cua hang",
    "hop tac xa",
    "xuat nhap khau",
    "thuong mai",
)

SALESPERSON_MARKERS = (
    "nvbh",
    "ten nv",
    "nhan vien",
    "sales",
    "giao nhan",
    "lai xe",
    "hrc",
)

GENERIC_SUPPLIER_TOKENS = {
    "cong",
    "ty",
    "cty",
    "tnhh",
    "tm",
    "tmdv",
    "xnk",
    "thuong",
    "mai",
    "xuat",
    "nhap",
    "khau",
    "co",
    "phan",
    "chi",
    "nhanh",
    "doanh",
    "nghiep",
    "cua",
    "hang",
    "hop",
    "tac",
    "xa",
    "viet",
    "nam",
    "da",
    "nang",
}


def _clean(value):
    text = str(value or "").strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value):
    return [token for token in _clean(value).split() if token]


def _meaningful_supplier_tokens(value):
    return [
        token
        for token in _tokens(value)
        if token not in GENERIC_SUPPLIER_TOKENS and len(token) >= 2
    ]


def _has_company_marker(value):
    clean = _clean(value)
    return any(marker in clean for marker in COMPANY_MARKERS)


def _looks_like_salesperson_text(value):
    clean = _clean(value)
    if not clean:
        return False
    if _has_company_marker(clean):
        return False
    return any(marker in clean for marker in SALESPERSON_MARKERS)


def _best_evidence_line(text, matched_tokens):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return str(text or "").strip()

    best_line = lines[0]
    best_score = -1
    for line in lines:
        line_clean = _clean(line)
        score = sum(1 for token in matched_tokens if token in line_clean)
        if _has_company_marker(line):
            score += 2
        if score > best_score:
            best_line = line
            best_score = score
    return best_line


def _score_supplier_text_match(text, code, supplier_name):
    clean_text = _clean(text)
    clean_code = _clean(code)
    clean_name = _clean(supplier_name)

    if not clean_text or _looks_like_salesperson_text(text):
        return None

    if clean_name and clean_name in clean_text:
        return 0.97, _meaningful_supplier_tokens(supplier_name) or [clean_name]

    meaningful = _meaningful_supplier_tokens(supplier_name)
    if not meaningful:
        return None

    matched = [token for token in meaningful if token in clean_text]
    if not matched:
        return None

    if clean_code and re.search(rf"\b{re.escape(clean_code)}\b", clean_text):
        confidence = 0.90
    else:
        required = len(meaningful)
        matched_ratio = len(matched) / required
        if len(meaningful) <= 2:
            if len(matched) < len(meaningful):
                return None
            confidence = 0.90
        elif matched_ratio < 0.70:
            return None
        else:
            confidence = 0.86 + min(0.09, matched_ratio * 0.09)

    if not _has_company_marker(text) and confidence < 0.92:
        return None

    return min(confidence, 0.97), matched


def extract_supplier_candidates_from_text(text, data_store, source):
    if not str(text or "").strip() or _looks_like_salesperson_text(text):
        return []

    candidates = []
    for code, supplier_name in getattr(data_store, "suppliers_dict", {}).items():
        match = _score_supplier_text_match(text, code, supplier_name)
        if not match:
            continue
        confidence, matched_tokens = match
        candidates.append({
            "code": str(code).strip(),
            "raw_text": _best_evidence_line(text, matched_tokens),
            "confidence": round(float(confidence), 3),
            "source": source,
            "evidence": matched_tokens,
        })

    candidates.sort(key=lambda row: row["confidence"], reverse=True)
    return candidates


def should_rescue_supplier(invoice_json):
    supplier = (invoice_json or {}).get("supplier_info") or {}
    code = str(supplier.get("supplier_name_code") or "").strip()
    raw = str(supplier.get("supplier_name_raw") or "").strip()
    return not code or _looks_like_salesperson_text(raw)


def apply_rescue_evidence(invoice_json, rescue_report):
    updated = copy.deepcopy(invoice_json or {})
    candidates = (rescue_report or {}).get("supplier_candidates") or []
    best = candidates[0] if candidates else None
    if not best or float(best.get("confidence") or 0.0) < MIN_SUPPLIER_RESCUE_CONFIDENCE:
        return updated

    supplier = updated.setdefault("supplier_info", {})
    supplier["supplier_name_code"] = best.get("code")
    supplier["supplier_name_raw"] = best.get("raw_text") or best.get("code")

    metadata = updated.setdefault("_local_evidence_rescue", {})
    metadata["supplier"] = {
        "code": best.get("code"),
        "raw_text": best.get("raw_text"),
        "confidence": best.get("confidence"),
        "source": best.get("source"),
        "evidence": best.get("evidence") or [],
    }
    return updated


def _crop_header_regions(image):
    if image is None or not hasattr(image, "crop"):
        return []

    width, height = image.size
    if width <= 0 or height <= 0:
        return []

    regions = [
        ("header_top_40", (0, 0, width, max(1, int(height * 0.40)))),
        ("header_left_55", (0, 0, max(1, int(width * 0.70)), max(1, int(height * 0.55)))),
    ]
    return [(name, image.crop(box)) for name, box in regions]


def _ocr_crop_default(crop_image, stop_event=None, status_callback=None):
    from module_paddle_ocr import get_paddle_engine

    fd, image_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        crop_image.save(image_path, quality=95)
        raw_text, confidence = get_paddle_engine().extract_raw_text(
            image_path,
            stop_event=stop_event,
            status_callback=status_callback,
        )
        return raw_text, confidence
    finally:
        try:
            os.remove(image_path)
        except OSError:
            pass


def run_local_evidence_rescue(
    invoice_json,
    normalized_structure,
    image,
    data_store,
    stop_event=None,
    status_callback=None,
    ocr_text_fn=None,
):
    report = {
        "supplier_candidates": [],
        "sources_checked": [],
    }
    if not should_rescue_supplier(invoice_json):
        return report

    raw_text = str((normalized_structure or {}).get("raw_text") or "")
    if raw_text.strip():
        report["sources_checked"].append("structure_text")
        report["supplier_candidates"].extend(
            extract_supplier_candidates_from_text(raw_text, data_store, "structure_text")
        )

    if report["supplier_candidates"]:
        report["supplier_candidates"].sort(key=lambda row: row["confidence"], reverse=True)
        return report

    ocr_fn = ocr_text_fn or _ocr_crop_default
    for source_name, crop in _crop_header_regions(image):
        if stop_event and stop_event.is_set():
            break
        try:
            if status_callback:
                status_callback(f"Dang kiem tra lai vung dau hoa don: {source_name}")
            crop_text, crop_confidence = ocr_fn(crop, stop_event=stop_event, status_callback=status_callback)
        except Exception as exc:
            report.setdefault("errors", []).append(f"{source_name}: {type(exc).__name__}: {exc}")
            continue

        report["sources_checked"].append(source_name)
        candidates = extract_supplier_candidates_from_text(crop_text, data_store, source_name)
        for candidate in candidates:
            candidate["ocr_confidence"] = round(float(crop_confidence or 0.0), 3)
        report["supplier_candidates"].extend(candidates)
        if report["supplier_candidates"]:
            break

    report["supplier_candidates"].sort(key=lambda row: row["confidence"], reverse=True)
    return report
