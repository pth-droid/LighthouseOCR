import json
import os
import re
import time

from departments import VALID_DEPARTMENTS


def _should_keep_processing(stop_event):
    return not (stop_event and stop_event.is_set())


def _validation_confidence(validation_report):
    try:
        return float(validation_report.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _missing_vision_critical_fields(validation_report):
    missing = set(validation_report.get("missing_required_fields") or [])
    return bool(missing.intersection({"items", "total_amount"}))


def _should_use_direct_vision_fallback(validation_report):
    return (
        _missing_vision_critical_fields(validation_report)
        and _validation_confidence(validation_report) < 0.50
    )


def _should_use_vision_after_light_fallback(validation_report):
    return _missing_vision_critical_fields(validation_report)


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


def _is_garbled_name(name):
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


def _garbled_name_ratio(invoice_json):
    items = invoice_json.get("items") or []
    if not items:
        return 0.0
    garbled = sum(1 for it in items if _is_garbled_name(it.get("product_name")))
    return garbled / len(items)


def _has_total_mismatch(invoice_json):
    totals = invoice_json.get("totals") or {}
    return bool(str(totals.get("total_discrepancy_warning") or "").strip())


def _looks_handwritten(invoice_json):
    doc = invoice_json.get("document_info") or {}
    itype = str(doc.get("invoice_type") or "").upper()
    if "HANDWRITTEN" in itype or "RETAIL" in itype:
        return True
    txn = invoice_json.get("transaction_info") or {}
    no_number = not str(txn.get("invoice_number") or "").strip()
    no_date = not str(txn.get("invoice_date") or "").strip()
    return no_number and no_date


def _should_escalate_weak_result(invoice_json, validation_report):
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


def _has_reviewable_invoice_data(invoice_json):
    return bool(invoice_json.get("items") or [])


def _clean_for_pipeline_check(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9À-ỹ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _supplier_looks_suspicious_after_light_fallback(invoice_json, validation_before_light):
    missing_before = set((validation_before_light or {}).get("missing_required_fields") or [])
    if "supplier_name_code" not in missing_before:
        return False

    supplier = invoice_json.get("supplier_info") or {}
    supplier_code = str(supplier.get("supplier_name_code") or "").strip()
    supplier_raw = str(supplier.get("supplier_name_raw") or "").strip()
    if not supplier_code:
        return False

    raw_clean = _clean_for_pipeline_check(supplier_raw)
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


def _count_numbered_item_rows(normalized_structure):
    raw_text = str((normalized_structure or {}).get("raw_text") or "")
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    in_table = False
    row_numbers = set()
    header_markers = ("stt", "ten hang", "ten quy cach", "ma hang")
    total_markers = ("tong cong", "cong tien", "tong tien", "thue vat", "tien thue", "vat")

    for idx, line in enumerate(lines):
        clean = _clean_for_pipeline_check(line)
        if any(marker in clean for marker in header_markers):
            in_table = True
            continue
        if in_table and any(marker in clean for marker in total_markers):
            break
        if not in_table:
            continue

        match = re.fullmatch(r"0?([1-9]|[1-9][0-9])", clean)
        if not match:
            continue

        next_lines = []
        for next_line in lines[idx + 1: idx + 5]:
            next_clean_line = _clean_for_pipeline_check(next_line)
            if any(marker in next_clean_line for marker in total_markers):
                break
            next_lines.append(next_line)
        next_window = " ".join(next_lines)
        next_clean = _clean_for_pipeline_check(next_window)
        has_product_text = bool(re.search(r"[a-zÀ-ỹ]{3,}", next_clean))
        if has_product_text:
            row_numbers.add(int(match.group(1)))

    return len(row_numbers)


def _json_misses_detected_item_rows(invoice_json, normalized_structure):
    detected_rows = _count_numbered_item_rows(normalized_structure)
    actual_items = len(invoice_json.get("items") or [])
    return detected_rows >= 2 and actual_items < detected_rows


def _attach_local_evidence_report(invoice_json, rescue_report):
    if not rescue_report:
        return invoice_json
    metadata = invoice_json.setdefault("_local_evidence_rescue", {})
    metadata["sources_checked"] = rescue_report.get("sources_checked") or []
    metadata["supplier_candidates"] = rescue_report.get("supplier_candidates") or []
    if rescue_report.get("errors"):
        metadata["errors"] = rescue_report.get("errors")
    return invoice_json


def _run_supplier_evidence_rescue(
    invoice_json,
    normalized_structure,
    image,
    data_store,
    stop_event,
    status_callback,
):
    from local_evidence_rescue import (
        apply_rescue_evidence,
        run_local_evidence_rescue,
        should_rescue_supplier,
    )
    from supplier_enrichment import enrich_supplier

    if not should_rescue_supplier(invoice_json):
        return invoice_json

    rescue_report = run_local_evidence_rescue(
        invoice_json,
        normalized_structure,
        image,
        data_store,
        stop_event=stop_event,
        status_callback=status_callback,
    )
    candidates = rescue_report.get("supplier_candidates") or []
    if candidates:
        best = candidates[0]
        if status_callback:
            status_callback(
                "Tim thay bang chung NCC tu local evidence: "
                f"{best.get('code')} ({float(best.get('confidence') or 0.0):.0%})"
            )
        invoice_json = apply_rescue_evidence(invoice_json, rescue_report)
        invoice_json = enrich_supplier(invoice_json, data_store)
    else:
        if status_callback:
            status_callback("Khong co bang chung NCC du manh tu local evidence.")

    return _attach_local_evidence_report(invoice_json, rescue_report)


def _run_pro_vision_fallback(image, api_key, data_store, stop_event, status_callback, stage, validation_report):
    from module_pro_ocr import get_pro_ocr
    from supplier_enrichment import enrich_supplier

    pro_engine = get_pro_ocr(api_key, data_store)
    result = pro_engine.extract_image_directly(
        image,
        stop_event=stop_event,
        status_callback=status_callback,
    )
    result = enrich_supplier(result, data_store)
    result.setdefault("_structure_pipeline", {})
    result["_structure_pipeline"].update({
        "fallback_used": True,
        "pro_vision_fallback_used": True,
        "fallback_stage": stage,
        "validation_before_pro_vision": validation_report,
    })
    return result


def run_pipeline(input_dir: str, stop_event, api_key: str, signals) -> str:
    def _log(msg):
        signals.log.emit(msg)

    output_path = ""
    root_dir = input_dir.rstrip(os.sep).rstrip("/")

    valid_ext = (".png", ".jpg", ".jpeg")
    files = [f for f in os.listdir(root_dir) if f.lower().endswith(valid_ext)]

    if not files:
        _log("Khong tim thay anh nao trong thu muc da chon.")
        signals.status_txt.emit("Khong co anh!", "error")
        return output_path

    # Each run gets its own timestamped folder under OUTPUT/ (JSON + images + Excel).
    from output_paths import create_run_output_dir
    done_dir = create_run_output_dir()
    os.makedirs(done_dir, exist_ok=True)
    _log(f"Thu muc dau vao: {root_dir}")
    _log(f"Thu muc ket qua: {done_dir}")
    _log(f"PP-StructureV3 mac dinh: phat hien {len(files)} anh cho xu ly.")

    total = len(files)
    all_results = []

    for i, filename in enumerate(files, 1):
        if not _should_keep_processing(stop_event):
            break

        source_path = os.path.join(root_dir, filename)
        stem = os.path.splitext(filename)[0]
        dest_img_path = os.path.join(done_dir, filename)
        dest_json = os.path.join(done_dir, stem + ".json")
        processed_ok = False

        _log(f"[{i}/{total}] Dang chay PP-StructureV3: {filename}")
        signals.progress.emit(i - 1, total)
        signals.status_txt.emit(f"Dang xu ly {i}/{total}...", "running")

        try:
            import cv2
            import numpy as np

            from business_kie import BusinessKIE
            from core_rate_limiter import EngineCancellationError
            from data_manager import app_data
            from fallback_light_structurer import run_light_fallback, should_use_light_fallback
            from image_processor import prepare_image
            from invoice_json_builder import build_invoice_json
            from invoice_validation import validate_invoice_json
            from module_calculator import get_calculator
            from module_paddle_structure_ocr import get_structure_paddle_engine
            from structure_result_normalizer import normalize_structure_result
            from supplier_enrichment import enrich_supplier

            if not app_data.is_loaded:
                app_data.load_all()

            image = prepare_image(source_path)
            structure_input = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

            raw_structure = get_structure_paddle_engine().extract_structure(
                structure_input,
                stop_event=stop_event,
                status_callback=_log,
            )
            normalized = normalize_structure_result(raw_structure)
            kie_result = BusinessKIE(app_data).extract(normalized)
            json_rough = build_invoice_json(
                kie_result=kie_result,
                confidence_score=normalized.get("avg_confidence", 0.0),
            )
            json_rough = enrich_supplier(json_rough, app_data)
            json_rough = _run_supplier_evidence_rescue(
                json_rough,
                normalized,
                image,
                app_data,
                stop_event,
                _log,
            )
            validation = validate_invoice_json(json_rough)
            json_rough["_structure_pipeline"]["validation"] = validation

            if _should_use_direct_vision_fallback(validation):
                _log("Ket qua local qua yeu va thieu hang/tong tien -> dung Vision model nang.")
                json_rough = _run_pro_vision_fallback(
                    image,
                    api_key,
                    app_data,
                    stop_event,
                    _log,
                    "direct_after_structure",
                    validation,
                )
            elif should_use_light_fallback(validation):
                _log("Ket qua local con yeu -> dung model nhe lam fallback.")
                json_rough = run_light_fallback(
                    normalized,
                    normalized.get("avg_confidence", 0.0),
                    api_key,
                    app_data,
                    stop_event=stop_event,
                    status_callback=_log,
                )
                light_supplier_suspicious = _supplier_looks_suspicious_after_light_fallback(json_rough, validation)
                json_rough = enrich_supplier(json_rough, app_data)
                json_rough = _run_supplier_evidence_rescue(
                    json_rough,
                    normalized,
                    image,
                    app_data,
                    stop_event,
                    _log,
                )
                light_validation = validate_invoice_json(json_rough)
                json_rough.setdefault("_structure_pipeline", {})
                json_rough["_structure_pipeline"]["validation"] = light_validation
                json_rough["_structure_pipeline"]["light_fallback_used"] = True
                json_rough["_structure_pipeline"]["validation_before_light_fallback"] = validation
                if _should_use_vision_after_light_fallback(light_validation):
                    _log("Fallback nhe van thieu hang/tong tien -> dung Vision model nang.")
                    json_rough = _run_pro_vision_fallback(
                        image,
                        api_key,
                        app_data,
                        stop_event,
                        _log,
                        "after_light_fallback",
                        light_validation,
                    )
                    json_rough["_structure_pipeline"]["light_fallback_used"] = True
                    json_rough["_structure_pipeline"]["validation_before_light_fallback"] = validation
                elif light_supplier_suspicious:
                    _log("Fallback nhe co NCC dang nghi tu dong NVBH/HRC -> bo qua neu khong co bang chung local.")
            else:
                _log("Ket qua local du manh -> khong can fallback model nhe.")

            calc_engine = get_calculator(api_key, app_data)
            invoice_json = calc_engine.run_calculation(
                json_rough,
                stop_event=stop_event,
                status_callback=_log,
            )
            if not _has_reviewable_invoice_data(invoice_json):
                raise RuntimeError(
                    "Khong trich xuat duoc dong hang nao sau tat ca fallback; "
                    "giu anh trong INPUT de xu ly lai."
                )
            invoice_json.setdefault("_structure_pipeline", {})
            invoice_json["_structure_pipeline"].update(json_rough.get("_structure_pipeline", {}))

            invoice_json["_source_filename"] = filename
            # Carry supplier/evidence trace forward so the saved route is complete,
            # then stamp which actual pipeline path produced this result.
            for _trace_key in ("_supplier_resolution", "_local_evidence_rescue"):
                if _trace_key in json_rough and _trace_key not in invoice_json:
                    invoice_json[_trace_key] = json_rough[_trace_key]
            from pipeline_trace import build_route
            invoice_json["_processing_route"] = build_route(invoice_json, "structure_default")
            with open(dest_json, "w", encoding="utf-8") as jf:
                json.dump(invoice_json, jf, ensure_ascii=False, indent=2)

            all_results.append(invoice_json)
            confidence = invoice_json.get("document_info", {}).get("confidence_score", 1.0)
            supplier = invoice_json.get("supplier_info", {}).get("supplier_name_code", "?")
            conf_str = f"{confidence:.0%}" if isinstance(confidence, (float, int)) else str(confidence)
            _log(f"Xong: {filename} | NCC: {supplier} | Confidence: {conf_str}")
            processed_ok = True
        except Exception as e:
            err_name = type(e).__name__
            if err_name == "EngineCancellationError":
                _log("Da dung theo lenh nguoi dung.")
                break
            if os.path.exists(dest_json):
                try:
                    os.remove(dest_json)
                except OSError:
                    pass
            err_lines = str(e).splitlines()
            _log(f"Loi [{filename}]: {err_lines[0] or 'Loi khong xac dinh'}")
            for line in err_lines[1:]:
                if line.strip():
                    _log(f"   -> {line.strip()}")

        if processed_ok:
            try:
                ext = os.path.splitext(filename)[1].lower()
                if ext in (".jpg", ".jpeg"):
                    image.save(dest_img_path, quality=95)
                else:
                    image.save(dest_img_path)
                if os.path.normpath(source_path) != os.path.normpath(dest_img_path):
                    os.remove(source_path)
            except Exception as mv_err:
                _log(f"Khong luu duoc anh xu ly '{filename}': {mv_err}")
        else:
            _log(f"Giu lai anh loi trong thu muc dau vao: {filename}")

        signals.progress.emit(i, total)

        if i < total and _should_keep_processing(stop_event):
            delay = 1
            _log(f"Cho {delay}s truoc khi tiep tuc...")
            for remaining in range(delay, 0, -1):
                if not _should_keep_processing(stop_event):
                    break
                signals.status_txt.emit(f"Nghi {remaining}s...", "running")
                time.sleep(1)

    if all_results:
        _log(f"Dang ghi {len(all_results)} hoa don vao Excel...")
        try:
            from core_excel_mapper import append_invoices_to_excel
            from data_manager import app_data

            output_raw = append_invoices_to_excel(
                all_results,
                data_store=app_data,
                api_key=api_key,
                output_dir=done_dir,
                status_callback=_log,
            )
            output_list = output_raw.split("|")
            for f_path in output_list:
                _log(f"File ket qua: {os.path.basename(f_path)}")
            output_path = output_raw
        except PermissionError as pe:
            signals.error.emit("Loi File Excel", str(pe))
            return output_path
        except FileNotFoundError as fnf:
            signals.error.emit("Thieu File Mau", str(fnf))
            return output_path
    else:
        if _should_keep_processing(stop_event):
            _log("Khong co hoa don nao duoc xu ly thanh cong.")

    if output_path:
        _log("Hoan tat. Dang mo giao dien ra soat ket qua...")
        signals.status_txt.emit(f"Hoan thanh - {len(all_results)}/{total} hoa don", "done")
    else:
        if _should_keep_processing(stop_event):
            signals.status_txt.emit("Da dung.", "idle")

    return output_path
