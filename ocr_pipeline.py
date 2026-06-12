"""
ocr_pipeline.py
Standalone OCR pipeline logic extracted from OCRWorker._run_pipeline.
"""

import os
import json
import shutil
import time


def run_pipeline(input_dir: str, stop_event, api_key: str, signals, dept_map=None) -> str:
    """
    Run the full OCR → Excel pipeline.

    Args:
        input_dir:  Path to the folder containing input images.
        stop_event: threading.Event used to signal cancellation.
        api_key:    Gemini API key.
        dept_map:   Optional {filename: department} from the pre-scan tagging
                    dialog. Accepted for signature parity with the structure
                    pipeline; legacy mode does not apply it.
        signals:    WorkerSignals instance (log, log_ow, progress, status_txt, finished, error).

    Returns:
        Output file path string (pipe-separated if multiple), or "" if nothing was produced.
    """
    def _log(msg):
        signals.log.emit(msg)

    output_path = ""

    root_dir = input_dir.rstrip(os.sep).rstrip('/')

    valid_ext = ('.png', '.jpg', '.jpeg')
    files = [f for f in os.listdir(root_dir) if f.lower().endswith(valid_ext)]

    if not files:
        _log("⚠️ Không tìm thấy ảnh nào trong thư mục đã chọn.")
        signals.status_txt.emit("Không có ảnh!", "error")
        return output_path

    # Each run gets its own timestamped folder under OUTPUT/ (JSON + images + Excel).
    from output_paths import create_run_output_dir
    done_dir = create_run_output_dir()
    os.makedirs(done_dir, exist_ok=True)
    _log(f"📁 Thư mục đầu vào: {root_dir}")
    _log(f"📂 Thư mục kết quả: {done_dir}")
    _log(f"📦 Đã phát hiện {len(files)} hình ảnh chờ xử lý.")

    total = len(files)
    all_results = []

    for i, filename in enumerate(files, 1):
        if stop_event.is_set():
            break

        source_path   = os.path.join(root_dir, filename)
        stem          = os.path.splitext(filename)[0]
        dest_img_path = os.path.join(done_dir, filename)
        dest_json     = os.path.join(done_dir, stem + ".json")
        processed_ok  = False

        _log(f"⏳ [{i}/{total}] Đang OCR: {filename}")
        signals.progress.emit(i - 1, total)
        signals.status_txt.emit(f"Đang xử lý {i}/{total}...", "running")

        try:
            from data_manager import app_data
            from module_paddle_ocr import get_paddle_engine
            from module_flash_ocr import get_flash_structurer
            from module_pro_ocr import get_pro_ocr
            from module_calculator import get_calculator
            from image_processor import prepare_image
            from core_rate_limiter import EngineCancellationError

            if not app_data.is_loaded:
                app_data.load_all()

            image = prepare_image(source_path)

            paddle_engine = get_paddle_engine()

            # Convert PIL Image to OpenCV BGR array for PaddleOCR
            import cv2
            import numpy as np
            paddle_input_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

            raw_text, avg_conf = paddle_engine.extract_raw_text(
                paddle_input_img, stop_event=stop_event,
                status_callback=_log
            )

            # Trace which actual legacy path this invoice takes.
            legacy_primary = None
            legacy_pro_vision = False
            legacy_reason = None

            if avg_conf > 0.90:
                _log("🔀 Phân luồng In (1A): Độ tin cậy cao → Flash Structurer")
                legacy_primary = "flash_structurer"
                flash_engine = get_flash_structurer(api_key, app_data)
                json_rough = flash_engine.structure_text_to_json(
                    raw_text, avg_conf,
                    stop_event=stop_event, status_callback=_log
                )

                # Safety fallback: dùng hard-case score để quyết định Pro Vision
                raw_lines = [line for line in (raw_text or "").splitlines() if line.strip()]
                raw_line_count = len(raw_lines)
                invoice_type = str((json_rough.get("document_info", {}) or {}).get("invoice_type", "") or "").upper()
                item_count = len(json_rough.get("items", []) or [])

                hard_case_score = 0
                if raw_line_count >= 9:
                    hard_case_score += 1
                if avg_conf < 0.90:
                    hard_case_score += 1
                if not invoice_type or invoice_type.startswith("HANDWRITTEN"):
                    hard_case_score += 1

                if hard_case_score >= 2:
                    _log(
                        "🔁 Hard-case score >= 2 "
                        f"(lines={raw_line_count}, conf={avg_conf:.1%}, type={invoice_type or 'UNKNOWN'}, items={item_count}) "
                        "→ fallback Pro Vision"
                    )
                    legacy_pro_vision = True
                    legacy_reason = "hard_case"
                    pro_engine = get_pro_ocr(api_key, app_data)
                    json_rough = pro_engine.extract_image_directly(
                        image, stop_event=stop_event, status_callback=_log
                    )
            else:
                legacy_primary = "pro_vision_direct"
                legacy_pro_vision = True
                if raw_text == "":
                    _log("🔀 Phân luồng Ảnh (1B): Không đọc được chữ → AI Pro Vision")
                    legacy_reason = "no_text"
                else:
                    _log(f"🔀 Phân luồng Viết tay (1B): Tin cậy {avg_conf:.1%} → AI Pro")
                    legacy_reason = "handwritten"
                pro_engine = get_pro_ocr(api_key, app_data)
                json_rough = pro_engine.extract_image_directly(
                    image, stop_event=stop_event, status_callback=_log
                )

            calc_engine  = get_calculator(api_key, app_data)
            invoice_json = calc_engine.run_calculation(
                json_rough, stop_event=stop_event, status_callback=_log
            )

            invoice_json["_source_filename"] = filename
            # Record which actual legacy path produced this result, then stamp route.
            invoice_json.setdefault("_structure_pipeline", {}).update({
                "engine_primary": legacy_primary,
                "pro_vision_fallback_used": legacy_pro_vision,
                "legacy_reason": legacy_reason,
            })
            from pipeline_trace import build_route
            invoice_json["_processing_route"] = build_route(invoice_json, "legacy_hybrid")
            with open(dest_json, "w", encoding="utf-8") as jf:
                json.dump(invoice_json, jf, ensure_ascii=False, indent=2)

            all_results.append(invoice_json)
            confidence = invoice_json.get("document_info", {}).get("confidence_score", 1.0)
            supplier   = invoice_json.get("supplier_info", {}).get("supplier_name_code", "?")
            conf_str   = f"{confidence:.0%}" if isinstance(confidence, (float, int)) else str(confidence)
            _log(f"✅ Xong: {filename} | NCC: {supplier} | Confidence: {conf_str}")
            processed_ok = True

        except Exception as e:
            err_name = type(e).__name__
            # Check cancellation by name to avoid import issues
            if err_name == "EngineCancellationError":
                _log("🛑 Đã dừng theo lệnh người dùng.")
                break
            if os.path.exists(dest_json):
                try:
                    os.remove(dest_json)
                except OSError:
                    pass
            # Log ALL lines of the exception — do not truncate so subprocess stderr is visible
            err_lines = str(e).splitlines()
            _log(f"❌ Lỗi [{filename}]: {err_lines[0] or 'Lỗi không xác định'}")
            for line in err_lines[1:]:
                if line.strip():
                    _log(f"   ↳ {line.strip()}")

        if processed_ok:
            try:
                shutil.move(source_path, dest_img_path)
            except Exception as mv_err:
                _log(f"⚠️ Không di chuyển được '{filename}': {mv_err}")
        else:
            _log(f"↩️ Giữ lại ảnh lỗi trong thư mục đầu vào: {filename}")

        signals.progress.emit(i, total)

        # Delay between images
        if i < total and not stop_event.is_set():
            delay = 1
            _log(f"⏸ Chờ {delay}s trước khi tiếp tục...")
            for remaining in range(delay, 0, -1):
                if stop_event.is_set():
                    break
                signals.status_txt.emit(f"Nghỉ {remaining}s...", "running")
                time.sleep(1)

    # --- END OF LOOP ---
    # Write Excel (Only once at the end)
    if all_results:
        _log(f"📊 Đang ghi {len(all_results)} hóa đơn vào Excel...")
        try:
            from core_excel_mapper import append_invoices_to_excel
            from data_manager import app_data
            output_raw = append_invoices_to_excel(
                all_results, data_store=app_data, api_key=api_key,
                output_dir=done_dir,
                status_callback=_log
            )
            # Xử lý trường hợp trả về nhiều file
            output_list = output_raw.split('|')
            for f_path in output_list:
                _log(f"✅ File kết quả: {os.path.basename(f_path)}")

            output_path = output_raw
        except PermissionError as pe:
            signals.error.emit("Lỗi File Excel", str(pe))
            return output_path
        except FileNotFoundError as fnf:
            signals.error.emit("Thiếu File Mẫu", str(fnf))
            return output_path
    else:
        if not stop_event.is_set():
            _log("⚠️ Không có hóa đơn nào được xử lý thành công.")

    if output_path:
        _log("🎉 Hoàn tất! Đang mở giao diện rà soát kết quả...")
        signals.status_txt.emit(f"Hoàn thành — {len(all_results)}/{total} hóa đơn", "done")
    else:
        if not stop_event.is_set():
            signals.status_txt.emit("Đã dừng.", "idle")

    return output_path
