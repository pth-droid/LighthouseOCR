========================================================
       LIGHTHOUSE OCR - HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG
========================================================
Phiên bản: 6.2  |  Cập nhật: 2026-05-12

HỆ THỐNG YÊU CẦU
-----------------
- Windows 10/11 (64-bit)
- Kết nối Internet (cho lần cài đặt đầu tiên và API Gemini)
- Quyền Administrator (khuyến nghị cho bước cài VC++)


========================================================
  BƯỚC 1 — GIẢI NÉN
========================================================
Giải nén toàn bộ thư mục 'LighthouseOCR' ra ổ cứng.
Ví dụ: D:\LighthouseOCR

QUAN TRỌNG: Không để trong thư mục có tên chứa ký tự đặc biệt
hoặc đường dẫn quá dài (giới hạn Windows).


========================================================
  BƯỚC 2 — THIẾT LẬP MÔI TRƯỜNG (CHỈ CHẠY 1 LẦN)
========================================================
1. Vào thư mục 'LighthouseOCR'
2. Chuột phải vào file 'Setup_Moi_Truong.bat'
   → Chọn "Run as Administrator" (Chạy với quyền Quản trị)

Script sẽ tự động thực hiện:
  [1/3] Cài Microsoft Visual C++ Redistributable (nếu thiếu)
  [2/3] Tải Python 3.10 portable + cài PaddleOCR
  [3/3] Tải trước mô hình AI (~200 MB — cần Internet)

Thời gian: khoảng 5–15 phút tùy tốc độ mạng.

Khi hiện thông báo:
  ┌────────────────────────────────────────┐
  │   HE THONG DA SAN SANG!               │
  │   Ban co the chay LighthouseOCR.exe   │
  └────────────────────────────────────────┘
→ Nhấn phím bất kỳ để đóng cửa sổ.

Nếu không có quyền Admin:
  - Phần cài VC++ sẽ bị bỏ qua (không ảnh hưởng nếu máy đã có)
  - Phần Python và OCR vẫn tiếp tục bình thường


========================================================
  BƯỚC 3 — CHẠY CHƯƠNG TRÌNH
========================================================
Chạy file 'LighthouseOCR.exe' để mở giao diện chính.

Lần đầu chạy:
  → Nhấn biểu tượng ⚙ (bánh răng) ở góc trên phải
  → Nhập Gemini API Key vào ô tương ứng
  → Nhấn Lưu

Lấy API Key miễn phí tại: https://aistudio.google.com
(Đăng nhập bằng tài khoản Google, chọn "Get API Key")


========================================================
  HƯỚNG DẪN SỬ DỤNG CƠ BẢN
========================================================

1. QUÉT HÓA ĐƠN
   - Nhấn nút "Chọn thư mục ảnh" để chọn thư mục chứa ảnh hóa đơn
   - Hệ thống sẽ xử lý lần lượt từng ảnh:
     • Sửa chiều ảnh tự động (theo EXIF điện thoại)
     • Tăng chất lượng ảnh (khử nhiễu, tăng độ tương phản)
     • OCR nhận diện chữ (PaddleOCR + Gemini)
   - Kết quả ghi ra file Excel trong thư mục 'DONE'

2. XEM XÉT VÀ CHỈNH SỬA KẾT QUẢ
   - Sau khi quét xong, nhấn "Xem xét kết quả" để mở dialog
   - Tab PNMH: kiểm tra phiếu nhập mua hàng
   - Tab Chi Phí: kiểm tra phiếu nhập chi phí
   - Click vào dòng để xem ảnh hóa đơn bên phải
   - Cuộn chuột trên ảnh: zoom in/out
   - Giữ và kéo chuột trên ảnh: di chuyển
   - Chuột phải trên ảnh:
     • Mở thư mục chứa ảnh trong Explorer (và chọn file)
     • Xoay ảnh trái/phải 90°

3. LƯU VÀO TỪ ĐIỂN ALIAS
   Khi OCR nhận diện tên hàng chưa khớp với danh mục:
   a. Sửa cột "MÃ VẬT TƯ" cho đúng
   b. Chuột phải vào dòng → "Lưu vào Từ điển Alias"
   c. Xác nhận: Alias (tên OCR) + Tên chuẩn + ĐVT + Hệ số
   → Lần sau OCR tự động nhận diện đúng

4. XUẤT EXCEL
   - Nhấn nút "Lưu" trong dialog xem xét để ghi kết quả vào Excel
   - File Excel nằm trong thư mục 'DONE' cùng cấp với ảnh đầu vào


========================================================
  CÁC LƯU Ý QUAN TRỌNG
========================================================
- Thư mục 'Data structure': Chứa danh mục vật tư, nhà cung cấp.
  Không xóa hoặc đổi tên các file trong đây.

- Thư mục 'python_env': Được tạo bởi Setup_Moi_Truong.bat.
  Không xóa — đây là môi trường OCR offline.

- File kết quả Excel: Nằm trong thư mục 'DONE' tại cùng cấp
  với thư mục ảnh đầu vào.

- Internet: Cần kết nối để gọi API Gemini và để chạy Setup lần đầu.
  Sau khi setup xong, OCR PaddleOCR hoạt động hoàn toàn offline.


========================================================
  XỬ LÝ SỰ CỐ
========================================================
Lỗi "Môi trường OCR chưa được cài đặt":
  → Chạy lại Setup_Moi_Truong.bat

Ảnh hiển thị sai chiều:
  → Chuột phải vào ảnh trong dialog → Xoay trái/phải

OCR bị treo lâu (>2 phút):
  → Hệ thống tự ngắt sau 120 giây, thử lại ảnh đó

Gemini báo lỗi quota:
  → Đợi 1 phút rồi thử lại, hoặc kiểm tra API Key

========================================================
Lighthouse OCR — https://github.com/pth-droid/LighthouseOCR
Phiên bản: 6.2
========================================================
