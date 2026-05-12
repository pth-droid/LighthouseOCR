# LighthouseOCR

Ứng dụng OCR hóa đơn tự động cho nghiệp vụ nhập kho (PNMH) và nhập chi phí, sử dụng PaddleOCR + Google Gemini.

---

## Mục lục

1. [Cài đặt cho người dùng cuối (EXE)](#1-cài-đặt-cho-người-dùng-cuối-exe)
2. [Cài đặt từ mã nguồn (nhà phát triển)](#2-cài-đặt-từ-mã-nguồn-nhà-phát-triển)
3. [Cấu hình lần đầu](#3-cấu-hình-lần-đầu)
4. [Cấu trúc thư mục](#4-cấu-trúc-thư-mục)
5. [Tính năng chính](#5-tính-năng-chính)
6. [Build EXE từ source](#6-build-exe-từ-source)
7. [Xử lý sự cố](#7-xử-lý-sự-cố)

---

## 1. Cài đặt cho người dùng cuối (EXE)

### Yêu cầu

- Windows 10/11 64-bit
- Kết nối Internet (để tải Python và models trong lần đầu)

### Các bước

**Bước 1 — Giải nén gói cài đặt**

Giải nén toàn bộ thư mục `LighthouseOCR` ra ổ cứng. Ví dụ: `D:\LighthouseOCR`.

**Bước 2 — Thiết lập môi trường (chỉ làm 1 lần)**

1. Vào thư mục `LighthouseOCR`
2. Chuột phải vào `Setup_Moi_Truong.bat` → **"Run as Administrator"**
3. Script sẽ tự động:
   - Cài Microsoft Visual C++ Redistributable (nếu thiếu)
   - Tải Python 3.10 portable (`python_env/`)
   - Cài PaddleOCR 3.5.0 + PaddlePaddle 3.3.1
   - Tải trước mô hình AI (~200 MB)
4. Khi hiện `HE THONG DA SAN SANG!` → nhấn phím bất kỳ để đóng

> **Lưu ý:** Nếu không có quyền Admin, phần cài VC++ sẽ bỏ qua nhưng Python portable vẫn được cài bình thường.

**Bước 3 — Chạy ứng dụng**

Chạy `LighthouseOCR.exe` để mở giao diện chính.

**Bước 4 — Nhập Gemini API Key**

Lần đầu chạy, nhấn biểu tượng ⚙ (Settings) và nhập Gemini API Key.  
Lấy key miễn phí tại: https://aistudio.google.com

---

## 2. Cài đặt từ mã nguồn (nhà phát triển)

### Yêu cầu hệ thống

| Thành phần | Phiên bản | Ghi chú |
|-----------|-----------|---------|
| Python | **3.10.x** | PaddlePaddle 3.x yêu cầu Python 3.10 |
| Git | bất kỳ | để clone repo |
| Microsoft VC++ Redistributable | 2022 | [Tải tại đây](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| Tesseract OCR | 5.x | Tùy chọn — cho tính năng phát hiện góc xoay ảnh. [Tải tại đây](https://github.com/UB-Mannheim/tesseract/wiki) |

### Bước 1 — Clone repo

```bash
git clone https://github.com/pth-droid/LighthouseOCR.git
cd LighthouseOCR
```

### Bước 2 — Tạo môi trường ảo (khuyến nghị)

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
```

### Bước 3 — Cài đặt thư viện

```bash
# Thư viện UI + xử lý ảnh + Excel
pip install "numpy<2.0.0" opencv-python Pillow PyQt5 openpyxl

# Google Gemini SDK
pip install google-genai

# PaddlePaddle (từ index riêng của Paddle)
pip install "paddlepaddle==3.3.1" -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

# PaddleOCR
pip install "paddleocr==3.5.0"

# Tesseract wrapper (tùy chọn)
pip install pytesseract
```

### Bước 4 — Tải trước mô hình OCR (1 lần)

```bash
python ocr_runner.py --warmup
```

Mô hình (~200 MB) được lưu vào cache tại `~/.paddleocr/`.

### Bước 5 — Chạy ứng dụng

```bash
python main_app_qt.py
```

---

## 3. Cấu hình lần đầu

### Gemini API Key

- Nhấn ⚙ (Settings) trong giao diện chính
- Dán Gemini API Key vào ô tương ứng
- Key được mã hóa và lưu trong `lighthouse_config.json`
- Lấy key miễn phí tại: https://aistudio.google.com

### File alias từ điển

Mặc định nằm tại `Data structure/Tu_dien_alias.csv`.  
Có thể chỉ định file khác trong Settings để dùng chung qua mạng nội bộ.

---

## 4. Cấu trúc thư mục

```
LighthouseOCR/
├── main_app_qt.py          # Entry point
├── ocr_runner.py           # OCR subprocess (chạy qua python_env/)
├── image_processor.py      # Xử lý ảnh (EXIF, OSD, deskew, CLAHE)
├── post_process_dialog.py  # Dialog xem xét + chỉnh sửa dữ liệu OCR
├── core_excel_mapper.py    # Ghi kết quả ra Excel
├── data_manager.py         # Quản lý dữ liệu master + alias
├── module_paddle_ocr.py    # Wrapper gọi PaddleOCR qua subprocess
├── module_flash_ocr.py     # OCR nhanh qua Gemini Flash
├── module_pro_ocr.py       # OCR chuyên sâu qua Gemini Pro
├── app_style.qss           # Stylesheet UI
├── icon.ico                # Icon ứng dụng
├── pipeline.yaml           # Cấu hình luồng xử lý OCR
├── LighthouseOCR.spec      # PyInstaller build spec
├── Setup_Moi_Truong.bat    # Script cài đặt môi trường OCR (portable Python)
│
├── Data structure/         # Dữ liệu master (cần có khi chạy)
│   ├── Danh_sach_VT.xlsx   # Danh mục vật tư (Mã, Tên, ĐVT, Giá mua)
│   ├── Nha_cung_cap.xlsx   # Danh mục nhà cung cấp
│   ├── Tu_dien_alias.csv   # Từ điển alias OCR → tên chuẩn
│   └── ...
│
└── python_env/             # Python portable cho OCR (tạo bởi Setup_Moi_Truong.bat)
    └── python.exe
```

---

## 5. Tính năng chính

### Pipeline OCR

1. **Tiền xử lý ảnh** (`image_processor.py`):
   - Sửa xoay theo dữ liệu EXIF (ảnh chụp bằng điện thoại)
   - Phát hiện góc xoay bằng Tesseract OSD (tùy chọn)
   - Phát hiện biên hóa đơn + perspective transform
   - Deskew (chỉnh nghiêng ±15°)
   - Denoising, CLAHE, Sharpening

2. **PaddleOCR** (PP-OCRv5, chạy qua subprocess):
   - Nhận diện chữ tiếng Việt
   - Kết quả ghi ra JSON tạm

3. **Gemini AI**:
   - Flash OCR: phân tích nhanh toàn bộ hóa đơn
   - Pro OCR: phân tích chuyên sâu cho hóa đơn phức tạp
   - Tính toán hệ số quy đổi đơn vị, khớp tên vật tư

### Dialog xem xét (post_process_dialog.py)

- Bảng PNMH (Phiếu Nhập Mua Hàng) với đầy đủ cột Excel
- Bảng Chi Phí (Nhập chi phí hạch toán Nợ 6421 / Có 331)
- Panel xem ảnh hóa đơn với zoom (cuộn chuột), pan (kéo chuột trái)
- Menu chuột phải trên ảnh:
  - 📂 Mở thư mục chứa ảnh (reveal + chọn file trong Explorer)
  - ↩ Xoay trái 90° / ↪ Xoay phải 90° (lưu lại file)
- Menu chuột phải trên bảng PNMH:
  - 📝 Lưu vào Từ điển Alias

### Từ điển Alias

Khi OCR nhận diện sai tên hàng so với tên chuẩn trong hệ thống:

1. Sửa **MÃ VẬT TƯ** cho đúng trong bảng PNMH
2. Chuột phải vào dòng → **"Lưu vào Từ điển Alias"**
3. Xác nhận thông tin:
   - **Alias**: tên trên hóa đơn / OCR đọc được
   - **Tên chuẩn**: tra từ master list theo Mã VT
   - **ĐVT kho**: đơn vị tính từ master list
   - **ĐVT lóng**: đơn vị tính trên hóa đơn (nếu khác)
   - **Hệ số**: quy đổi từ lóng sang kho
4. Lần sau OCR gặp tên tương tự → tự động khớp đúng mã + đơn vị

---

## 6. Build EXE từ source

### Yêu cầu

```bash
pip install pyinstaller
```

### Build

```bash
pyinstaller LighthouseOCR.spec
```

Output tại `dist/LighthouseOCR/`. Phân phối toàn bộ thư mục này.

### Sau khi build

1. Copy thư mục `Data structure/` vào `dist/LighthouseOCR/` (nếu chưa có)
2. Copy `Setup_Moi_Truong.bat` vào `dist/LighthouseOCR/`
3. Người dùng cuối chạy `Setup_Moi_Truong.bat` để cài `python_env/`

> **Lưu ý:** `python_env/` không được bundle trong EXE — người dùng phải chạy bat để tạo nó.

---

## 7. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Giải pháp |
|------------|-------------|-----------|
| `Môi trường OCR chưa được cài đặt` | `python_env/` chưa có | Chạy `Setup_Moi_Truong.bat` |
| OCR bị treo > 2 phút | Subprocess PaddleOCR không phản hồi | Timeout tự động sau 120s; thử lại |
| Ảnh hiển thị sai chiều | EXIF không có hoặc Tesseract chưa cài | Dùng nút xoay trong context menu |
| `KeyError` khi mở dialog | File Excel trong `Data structure/` bị thiếu cột | Kiểm tra cấu trúc file theo mẫu |
| Gemini trả về lỗi 429 | Vượt quota API miễn phí | Đợi 1 phút hoặc nâng cấp gói Gemini |
| Không tìm thấy `Tu_dien_alias.csv` | Lần đầu chạy, file chưa tồn tại | File sẽ được tạo tự động khi lưu alias đầu tiên |
