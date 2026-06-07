import json
import os
import time


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


def _has_reviewable_invoice_data(invoice_json):
    return bool(invoice_json.get("items") or [])


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
    done_dir = os.path.join(os.path.dirname(root_dir), "DONE")

    valid_ext = (".png", ".jpg", ".jpeg")
    files = [f for f in os.listdir(root_dir) if f.lower().endswith(valid_ext)]

    if not files:
        _log("Khong tim thay anh nao trong thu muc da chon.")
        signals.status_txt.emit("Khong co anh!", "error")
        return output_path

    os.makedirs(done_dir, exist_ok=True)
    _log(f"Thu muc dau vao: {root_dir}")
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
                json_rough = enrich_supplier(json_rough, app_data)
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

            with open(dest_json, "w", encoding="utf-8") as jf:
                json.dump(invoice_json, jf, ensure_ascii=False, indent=2)

            invoice_json["_source_filename"] = filename
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
