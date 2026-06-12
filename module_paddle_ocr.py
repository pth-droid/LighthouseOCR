import logging
import os
import sys
import json
import subprocess
import tempfile
import time
from core_rate_limiter import EngineCancellationError
from path_utils import get_root_dir, get_asset_path


class LocalPaddleOCREngine:
    def __init__(self):
        """
        Khởi tạo Engine kết nối với môi trường Python ngoài (Hybrid Architecture).
        """
        self.python_env_dir = os.path.join(get_root_dir(), "env")
        if os.name == 'nt':
            self.python_exe = os.path.join(self.python_env_dir, "python.exe")
        else:
            self.python_exe = os.path.join(self.python_env_dir, "bin", "python")
        
        self.runner_script = get_asset_path("ocr_runner.py")
        self._runtime_version = None
        
        # Chỉ cảnh báo, không throw exception ở đây để App vẫn lên được UI
        if not os.path.exists(self.python_exe):
            print(f"Warning: Portable Python không tìm thấy tại {self.python_exe}")
        if not os.path.exists(self.runner_script):
            print(f"Warning: OCR runner script không tìm thấy tại {self.runner_script}")

    def _get_runtime_version(self) -> str:
        if self._runtime_version:
            return self._runtime_version
        if not os.path.exists(self.python_exe):
            self._runtime_version = "unknown"
            return self._runtime_version

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            result = subprocess.run(
                [self.python_exe, "-c", "import paddleocr; print(getattr(paddleocr, '__version__', 'unknown'))"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                startupinfo=startupinfo,
                timeout=15,
            )
            lines = (result.stdout or "").strip().splitlines()
            self._runtime_version = lines[-1].strip() if lines else "unknown"
        except Exception:
            self._runtime_version = "unknown"
        return self._runtime_version or "unknown"

    def _build_start_message(self, runtime_version: str) -> str:
        return f"🔍 Đang gọi Local AI PaddleOCR {runtime_version} (qua subprocess)..."

    def _build_completion_message(
        self,
        runtime_version: str,
        text_count: int,
        avg_confidence: float,
        elapsed_seconds: float,
    ) -> str:
        return (
            f"✅ PaddleOCR {runtime_version} thu thập được {text_count} dòng "
            f"(Tin cậy: {avg_confidence:.1%}) trong {elapsed_seconds:.2f}s"
        )

    def extract_raw_text(self, image_input, stop_event=None, status_callback=None) -> tuple[str, float]:
        """
        Gọi ocr_runner.py qua subprocess để tránh lỗi thư viện C++/Cython.
        """
        if not os.path.exists(self.python_exe):
             raise RuntimeError("Môi trường OCR chưa được cài đặt. Vui lòng chạy Setup_Moi_Truong.bat trước khi dùng.")
        if not os.path.exists(self.runner_script):
             raise RuntimeError(f"Không tìm thấy script OCR ocr_runner.py tại hệ thống.")

        runtime_version = self._get_runtime_version()
        if status_callback:
            status_callback(self._build_start_message(runtime_version))

        if stop_event and stop_event.is_set():
            raise EngineCancellationError("STOP_REQUESTED")

        # Xử lý input ảnh
        image_path = None
        is_temp_image = False
        import numpy as np
        
        if isinstance(image_input, np.ndarray):
            import cv2
            fd, image_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            cv2.imwrite(image_path, image_input)
            is_temp_image = True
        elif isinstance(image_input, str):
            image_path = image_input
        else:
             raise ValueError("Unsupported image input type for subprocess OCR.")

        # Tạo file tạm cho output JSON
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        try:
            started_at = time.perf_counter()
            # Ẩn cửa sổ Console đen hiện lên khi gọi subprocess trên Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

            # Clean environment for subprocess to avoid PyInstaller conflicts
            sub_env = os.environ.copy()
            sub_env.pop('PYTHONHOME', None)
            sub_env.pop('PYTHONPATH', None)
            sub_env['PYTHONDONTWRITEBYTECODE'] = '1'

            # stdout is DEVNULL because all results go to the output_path JSON file.
            # This prevents a pipe-buffer deadlock: PaddleOCR writes initialization
            # output to stdout, and if the ~65 KB OS pipe buffer fills while the parent
            # is polling (not reading), both sides block forever. stderr stays as PIPE
            # (short tracebacks only) so we can report errors.
            process = subprocess.Popen(
                [self.python_exe, self.runner_script, image_path, output_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='ignore',
                env=sub_env
            )

            # Đợi process chạy, cho phép ngắt (cancel)
            while True:
                if stop_event and stop_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise EngineCancellationError("STOP_REQUESTED")
                if process.poll() is not None:
                    break
                time.sleep(0.1)

            _, stderr = process.communicate()

            if process.returncode != 0:
                 raise RuntimeError(f"Lỗi chạy OCR subprocess (Code {process.returncode}):\n[STDERR]: {stderr}")

            if not os.path.exists(output_path):
                 raise RuntimeError("Không có kết quả JSON trả về từ engine OCR độc lập.")
                 
            with open(output_path, 'r', encoding='utf-8') as f:
                 data = json.load(f)
                 
            texts = data.get("texts", [])
            confidences = data.get("scores", [])
            elapsed_seconds = time.perf_counter() - started_at
            raw_text_string = "\n".join(texts)
            avg_confidence  = sum(confidences) / len(confidences) if confidences else 0.0

            if status_callback:
                status_callback(self._build_completion_message(runtime_version, len(texts), avg_confidence, elapsed_seconds))

            if not texts:
                return "", 0.0

            return raw_text_string, avg_confidence

        finally:
            if is_temp_image and image_path and os.path.exists(image_path):
                try: os.remove(image_path)
                except: pass
            if output_path and os.path.exists(output_path):
                try: os.remove(output_path)
                except: pass

_paddle_instance = None

def get_paddle_engine():
    global _paddle_instance
    if not _paddle_instance:
        _paddle_instance = LocalPaddleOCREngine()
    return _paddle_instance
