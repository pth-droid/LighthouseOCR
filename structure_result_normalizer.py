def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _extract_tokens(payload):
    tokens = []
    for data in _iter_dicts(payload):
        texts = data.get("rec_texts") or data.get("texts")
        if not isinstance(texts, list):
            continue
        scores = data.get("rec_scores") or data.get("scores") or []
        boxes = data.get("rec_boxes") or data.get("dt_polys") or data.get("boxes") or []
        for idx, text in enumerate(texts):
            clean_text = str(text).strip()
            if not clean_text:
                continue
            try:
                confidence = float(scores[idx])
            except (IndexError, TypeError, ValueError):
                confidence = None
            try:
                bbox = boxes[idx]
            except (IndexError, TypeError):
                bbox = None
            tokens.append({"text": clean_text, "confidence": confidence, "bbox": bbox})
    return tokens


def _extract_regions(payload):
    regions = []
    for data in _iter_dicts(payload):
        candidates = []
        layout = data.get("layout_det_res")
        if isinstance(layout, dict):
            candidates.extend(_as_list(layout.get("boxes")))
        candidates.extend(_as_list(data.get("layout_result")))
        for box in candidates:
            if not isinstance(box, dict):
                continue
            label = box.get("label") or box.get("category") or box.get("type") or "unknown"
            bbox = box.get("coordinate") or box.get("bbox") or box.get("box")
            regions.append({"label": label, "bbox": bbox, "score": box.get("score")})
    return regions


def _extract_tables(payload):
    tables = []
    for data in _iter_dicts(payload):
        for key in ("table_res_list", "table_result", "tables"):
            value = data.get(key)
            for table in _as_list(value):
                if table:
                    tables.append(table)
    return tables


def normalize_structure_result(raw_result):
    raw_result = raw_result or {}
    pages = raw_result.get("pages", []) if isinstance(raw_result, dict) else []
    tokens = []
    regions = []
    tables = []
    for page in pages:
        tokens.extend(_extract_tokens(page))
        regions.extend(_extract_regions(page))
        tables.extend(_extract_tables(page))

    raw_text = raw_result.get("raw_text") if isinstance(raw_result, dict) else ""
    if not raw_text:
        raw_text = "\n".join(token["text"] for token in tokens)

    return {
        "engine": raw_result.get("engine", "PPStructureV3") if isinstance(raw_result, dict) else "PPStructureV3",
        "pages": pages,
        "raw_text": raw_text or "",
        "tokens": tokens,
        "regions": regions,
        "tables": tables,
        "avg_confidence": float(raw_result.get("avg_confidence") or 0.0) if isinstance(raw_result, dict) else 0.0,
    }
