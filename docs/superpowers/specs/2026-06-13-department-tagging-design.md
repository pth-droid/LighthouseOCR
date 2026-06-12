# Thiết kế: Dialog gán Bộ phận trước Scan + Leo thang Pro Vision cho hóa đơn yếu

- **Ngày:** 2026-06-13
- **Phiên bản app liên quan:** sau v7.5
- **Trạng thái:** Đã duyệt thiết kế, chờ lập kế hoạch hiện thực

## 1. Bối cảnh & Mục tiêu

Kết quả so sánh 3 bộ dữ liệu trong `DONE/` (LLM chat vs app input nguyên vs app input đã đánh dấu bộ phận) cho thấy:

- **Hóa đơn IN:** app gần như ngang LLM chat về số liệu/tổng tiền (đặc biệt khi đã leo thang Pro Vision — ca Moonmilk trùng khít 100%).
- **Hóa đơn VIẾT TAY:** app thua xa LLM chat. Pipeline PP-Structure → light fallback (chỉ đọc text đã méo) cho ra tên rác (`cāB`, `xutg`, `B'd`, `10Hinh`), tráo số lượng/đơn giá, và có khi đọc nhầm dòng TỔNG thành một mặt hàng (`BaRo = 755.000`). Các ca này có `confidence ≈ 0.86` nên **không** chạm điều kiện leo thang Pro Vision hiện tại (chỉ leo thang khi thiếu hẳn items/total và conf < 0.50).
- **Đánh dấu bộ phận thủ công** giúp: (a) tên hàng viết tay sạch hơn hẳn, (b) tránh map sai chí mạng (bản input nguyên map `cāB` → rượu vang `BAR95`), (c) khóa đúng cột BỘ PHẬN + KHO.

**Hai mục tiêu:**

1. **Dialog tiền xử lý gán bộ phận:** trước khi Scan, người dùng gán mỗi ảnh hóa đơn vào đúng 1 bộ phận (BEP/BAR/BANH/RANG) bằng phím tắt, có xem ảnh, tự nhảy ảnh kế. Bảo đảm mọi hóa đơn có bộ phận tin cậy ngay từ đầu.
2. **Nâng chuẩn leo thang Pro Vision:** thêm điều kiện để hóa đơn viết tay / tín hiệu yếu được đọc lại bằng Pro Vision (model vision), thay vì kẹt ở light fallback đọc text rác.

## 2. Quyết định đã chốt (với người dùng)

- Bộ phận: **đúng 4 loại `BEP / BAR / BANH / RANG`, BẮT BUỘC** gán cho mọi ảnh. Để chỗ mở cho lớp **Cửa hàng (Store) → Bộ phận** trong tương lai (chọn store trước, rồi mới chọn bộ phận) — *chưa* hiện thực store ở phiên này.
- Dialog **tự mở khi bấm Scan**; **hủy/đóng giữa chừng = hủy cả phiên scan** (không xử lý ảnh nào).
- Cách bộ phận vào pipeline: **Phương án A** — ghi đè `transaction_info.department` chính thức **và** bơm `department_hint` vào prompt của light fallback + Pro Vision (cải thiện cả độ chính xác đọc lẫn map).
- Leo thang Pro Vision: **Phương án A (cộng thêm predicate)** — "có dấu hiệu viết tay HOẶC tín hiệu yếu nói chung". Ngưỡng để chỗ chỉnh được.
- **Ngoài phạm vi:** xử lý VAT (việc gộp VAT vào đơn giá là *cố ý đơn giản hóa*, không phải lỗi).
- **Yêu cầu log:** mọi lỗi đều phải log rõ lý do, dù skip một ảnh hay stop cả phiên.

## 3. Phát hiện then chốt trong code hiện tại

- `transaction_info.department` **đã được dùng đầy đủ** ở hạ nguồn:
  - `core_excel_mapper.py:1626` — khi `department ∈ {BEP,BAR,BANH,RANG}` thì **khóa cứng** cột F (BỘ PHẬN) cho mọi item của hóa đơn đó và tra KHO NHẬP theo đó.
  - `item_matcher.py` / `core_excel_mapper.py` dùng `department_hint` làm tiêu chí ưu tiên (tier-1) khi match item (soft bias, không loại trừ cứng).
  - Đây khớp đúng ý "1 hóa đơn = 1 bộ phận". Việc còn thiếu chỉ là **nguồn bộ phận đáng tin** (do người dùng gán thay vì OCR đoán).
- Điều kiện leo thang Pro Vision nằm ở `ocr_pipeline_structure.py`:
  - `_should_use_direct_vision_fallback`: thiếu {items,total_amount} **và** conf < 0.50.
  - `_should_use_vision_after_light_fallback`: chỉ khi vẫn thiếu {items,total_amount}.
  - → Hóa đơn viết tay có items (dù rác) + conf ~0.86 **không** lọt vào leo thang.
- `invoice_type` do LLM light fallback gán **không đáng tin** (r12 viết tay bị gán `VAT_INVOICE`). ⇒ không được chỉ dựa vào nhãn này.
- Điểm khởi động scan: `main_app_qt.py` `_start_scan` (~dòng 1520) → `OCRWorker(input_dir, …)` → `run_pipeline(input_dir, stop_event, api_key, signals)`.

## 4. Thiết kế chi tiết

### 4.1. Dialog gán bộ phận — `department_tagging_dialog.py` (mới)

Tách 2 lớp để test được phần lõi:

- **`TaggingState`** (Python thuần, không Qt): danh sách tên file theo thứ tự, dict `{filename → dept}`, `current_index`.
  - `assign(dept)`: gán cho ảnh hiện tại + nhảy tới ảnh **chưa gán** kế tiếp.
  - `back()`, `goto(i)`.
  - `is_complete()`: True chỉ khi **mọi** ảnh đã gán 1 trong 4 dept hợp lệ.
  - `remaining()`, `assigned_count()`.
  - `get_department_map()`: trả `{basename → dept}`.
  - Bỏ qua dept không thuộc 4 loại hợp lệ.
- **`DepartmentTaggingDialog(QDialog)`**: lớp giao diện mỏng bọc `TaggingState`.
  - **Phải ~65%:** xem trước ảnh hóa đơn, scale-to-width (fit lại khi resize/show), fallback Pillow→QImage cho JPG (lỗi codec máy khách trong CLAUDE.md). Header: `Ảnh 3 / 12 — <tên file>`.
  - **Trái ~35%:**
    - Nhãn cửa hàng (1 store hiện tại) — *seam* cho lớp store sau này.
    - 4 nút lớn `[1] BEP / [2] BAR / [3] BANH / [4] RANG`; nút khớp gán hiện tại được tô sáng.
    - Tiến độ `Đã gán: 8 / 12`.
    - Danh sách cuộn mọi ảnh kèm badge bộ phận — **bấm để nhảy tới ảnh đó** (xem lại/sửa).
    - Nút chính `✅ Bắt đầu xử lý` (Enter) — **chỉ bật khi `is_complete()`**.
  - **Phím tắt:** `1–4` = gán + nhảy ảnh kế chưa gán; `←`/`Backspace` = ảnh trước; `→` = ảnh kế; click danh sách = nhảy thẳng; `Enter` = xác nhận (khi đủ); `Esc`/`[X]` = hỏi lại "Hủy toàn bộ phiên scan?" → `reject()`.
  - **Bước cuối:** sau khi gán ảnh cuối, **không** tự đóng — bật nút `Bắt đầu xử lý`, người dùng bấm `Enter` để chạy (cho phép xem/sửa ảnh cuối trước khi chạy).
  - `exec_() == Accepted` → `get_department_map()`.
- **Ngoài phạm vi (YAGNI):** xoay ảnh, zoom, UI chọn store, gán nhiều bộ phận / 1 hóa đơn.

### 4.2. Đường đi của bộ phận vào pipeline

- **`_start_scan` (`main_app_qt.py`):** sau preflight + kiểm `input_dir`, liệt kê ảnh bằng cùng bộ lọc đuôi như pipeline. Nếu rỗng → cảnh báo "Không có ảnh!" (không mở dialog). Ngược lại mở `DepartmentTaggingDialog`:
  - `reject()` → log `"Đã hủy phiên scan — chưa gán bộ phận."`, bật lại nút Scan, return (không tạo worker).
  - `accept()` → `dept_map = dlg.get_department_map()` → `OCRWorker(..., dept_map=dept_map)`.
- **`OCRWorker`:** thêm `dept_map: dict | None = None` vào `__init__`; truyền qua `_run_pipeline` vào `run_structure_pipeline(..., dept_map=self.dept_map)`. Pipeline legacy nhận cùng tham số (mặc định `None`) để giữ chữ ký; bản structure dùng đầy đủ, legacy ít nhất áp ghi đè metadata.
- **`run_pipeline(input_dir, stop_event, api_key, signals, dept_map=None)`** (`ocr_pipeline_structure.py`): mỗi ảnh `dept = (dept_map or {}).get(filename)`, hai điểm chèn:
  1. **Ghi đè chính thức** — helper `_apply_department_override(json_obj, dept)`:
     - Chỉ ghi khi `dept ∈ {BEP,BAR,BANH,RANG}`.
     - Set `transaction_info.department = dept` và `_department_source = "user_tag"`.
     - Gọi **sau `build_invoice_json`** và **lặp lại sau mỗi fallback** (light/Pro trả JSON mới) và sau leo thang.
  2. **Bơm ngữ cảnh đọc** — truyền `department_hint=dept` vào `run_light_fallback(...)` và `_run_pro_vision_fallback(...)`; prompt thêm dòng: *"Hóa đơn này thuộc bộ phận [BEP]. Ưu tiên đọc tên hàng theo nhóm hàng của bộ phận này."* Sửa chữ ký ở `fallback_light_structurer.py` và `module_pro_ocr.py` (`extract_image_directly(..., department_hint=None)`).
- **Trace:** `pipeline_trace.build_route` đọc thêm `_department_source` để 2 browser hiện "Bộ phận: BEP (gán tay)".

### 4.3. Predicate leo thang Pro Vision (`ocr_pipeline_structure.py`)

Cộng thêm, không đụng nhánh "thiếu items/total" đang đúng.

- **Hằng số (dễ chỉnh, có thể đưa ra `lighthouse_config.json` sau):**
  - `WEAK_HANDWRITTEN_CONF = 0.90`
  - `WEAK_ANY_CONF = 0.80`
  - `GARBLED_NAME_RATIO = 0.30`
- **Hàm phụ trợ:**
  - `_looks_handwritten(json)`: `invoice_type` chứa `HANDWRITTEN`/`RETAIL`, **hoặc** thiếu cả số hóa đơn lẫn ngày.
  - `_garbled_name_ratio(json)`: tỷ lệ item có tên "rác" — sau khi làm sạch: độ dài chữ cái ≤ 3, **hoặc** lẫn số với chữ, **hoặc** có ký tự lạ `' " \``, **hoặc** không có nguyên âm (kể cả nguyên âm có dấu).
  - `_has_total_mismatch(json)`: có `totals.total_discrepancy_warning`.
  - `_should_escalate_weak_result(json, validation)` → True nếu **bất kỳ**:
    - `_has_total_mismatch`,
    - `_garbled_name_ratio ≥ 0.30`,
    - `_looks_handwritten` **và** `conf < WEAK_HANDWRITTEN_CONF`,
    - `conf < WEAK_ANY_CONF`.
- **Cổng gộp** (đặt sau khối fallback if/elif/else hiện tại, trước calculator; chỉ chạy nếu chưa từng leo thang Pro):
  ```python
  da_pro = json_rough["_structure_pipeline"].get("pro_vision_fallback_used")
  val_now = json_rough["_structure_pipeline"].get("validation", validation)
  if not da_pro and _should_escalate_weak_result(json_rough, val_now):
      _log("Tín hiệu yếu / chữ viết tay -> nâng cấp Pro Vision.")
      json_rough = _run_pro_vision_fallback(image, api_key, app_data, stop_event,
                                            _log, "weak_signal_escalation", val_now,
                                            department_hint=dept)
      _apply_department_override(json_rough, dept)
  ```
- **Kỳ vọng trên 7 mẫu:** r12 (tên rác) + r10 28/5 (lệch tổng) → leo thang; Sáng Ngọc in conf 0.88 → không leo thang.
- **Chi phí:** Pro ~2 RPM + tính phí; `core_rate_limiter` vẫn điều tiết.

### 4.4. Xử lý lỗi & log

- Không có ảnh → cảnh báo cũ, không mở dialog.
- Ảnh hỏng trong dialog → ô giữ chỗ, **vẫn cho gán**; fallback Pillow→QImage.
- Hủy/đóng dialog → hỏi lại → `reject()` → không chạy worker (theo "cancel = abort").
- File không có trong `dept_map` (thêm sau khi mở dialog) → `dept=None` → quay về suy luận OCR + log lý do; không sập phiên.
- Pro Vision lỗi khi leo thang → rơi vào `try/except` theo ảnh sẵn có → **giữ ảnh trong INPUT** + log lý do, ảnh khác tiếp tục.
- `dept` không hợp lệ → `_apply_department_override` bỏ qua.
- **Nguyên tắc log (bắt buộc):** mọi lỗi log **đầy đủ lý do, không cắt dòng**, kèm tên file và **hành động**: phân biệt rõ `THÀNH CÔNG / BỎ QUA (kèm lý do) / DỪNG (kèm lý do)`. Pro Vision lỗi: `Pro Vision lỗi [file]: <lý do> → giữ ảnh lại`.
- **Tương thích ngược:** `dept_map=None` ở mọi nơi → hành vi y hệt hiện tại; pipeline legacy + test cũ không đổi; `_run_pro_vision_fallback`/`extract_image_directly` thêm `department_hint=None` mặc định.

## 5. Kiểm thử

- **`tests/test_tagging_state.py`** (lõi, không Qt): gán + auto-advance; `back/goto`; `is_complete()` chỉ True khi đủ; `get_department_map()` khóa theo basename; bỏ dept rác.
- **`tests/test_escalation_predicate.py`**: `_garbled_name_ratio` ≥0.30 với tên r12, =0 với tên in sạch; `_should_escalate_weak_result` True cho viết-tay-0.86 / lệch-tổng / tên-rác-gán-nhầm-VAT, False cho in-0.88. Fixture mô phỏng mẫu `DONE/`.
- **`tests/test_department_override.py`**: set field + `_department_source`, idempotent, bỏ dept rác, áp lại đúng sau khi thay bằng JSON Pro.
- **Cắm dây pipeline (test nhẹ, stub engine nặng):** `dept_map` thắng bộ phận OCR; `dept_map=None` giữ hành vi cũ.
- **TDD** khi hiện thực (đỏ trước, xanh sau).
- **Qt dialog**: kiểm thủ công theo checklist (phím tắt 1–4, nhảy/sửa qua danh sách, nút Bắt đầu chỉ bật khi đủ, Esc hủy).

## 6. Tệp bị ảnh hưởng

| Tệp | Thay đổi |
|---|---|
| `department_tagging_dialog.py` | **MỚI** — `TaggingState` + `DepartmentTaggingDialog` |
| `main_app_qt.py` | `_start_scan` mở dialog; `OCRWorker` nhận `dept_map`; truyền vào pipeline |
| `ocr_pipeline_structure.py` | nhận `dept_map`; `_apply_department_override`; predicate + cổng leo thang; bơm `department_hint` |
| `ocr_pipeline.py` (legacy) | nhận `dept_map=None`; ít nhất áp ghi đè metadata |
| `fallback_light_structurer.py` | `run_light_fallback(..., department_hint=None)` + dòng prompt |
| `module_pro_ocr.py` | `extract_image_directly(..., department_hint=None)` + dòng prompt |
| `pipeline_trace.py` | đọc `_department_source` để hiển thị "(gán tay)" |
| `tests/test_tagging_state.py` | **MỚI** |
| `tests/test_escalation_predicate.py` | **MỚI** |
| `tests/test_department_override.py` | **MỚI** |
| `CLAUDE.md` | changelog mục mới |

## 7. Tiêu chí hoàn thành (Definition of Done)

1. Bấm Scan → hiện dialog gán bộ phận; không gán đủ thì không chạy được; Esc hủy cả phiên (có log).
2. Bộ phận đã gán xuất hiện đúng ở cột F + KHO trong Excel cho mọi item của hóa đơn.
3. Light fallback & Pro Vision nhận được `department_hint` trong prompt.
4. Hóa đơn viết tay/tín hiệu yếu (mô phỏng r12, r10 28/5) kích hoạt leo thang Pro Vision; hóa đơn in tốt thì không.
5. Mọi lỗi log đầy đủ lý do + hành động (skip/stop).
6. `dept_map=None` → hành vi cũ không đổi (các test hiện có vẫn xanh).
7. Các test mới (tagging state, escalation predicate, override) xanh.
