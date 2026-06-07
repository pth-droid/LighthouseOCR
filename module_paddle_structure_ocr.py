import json
import os
import subprocess
import sys
import tempfile
import time

from core_rate_limiter import EngineCancellationError
from path_utils import get_asset_path, get_root_dir


class StructurePaddleOCREngine:
    def __init__(self):
        self.python_env_dir = os.path.join(get_root_dir(), "env")
        if os.name == "nt":
            self.python_exe = os.path.join(self.python_env_dir, "python.exe")
        else:
            self.python_exe = os.path.join(self.python_env_dir, "bin", "python")
        self.runner_script = get_asset_path("ocr_structure_runner.py")
        self.subprocess_timeout_seconds = int(os.environ.get("OCR_STRUCTURE_SUBPROCESS_TIMEOUT", "600"))

    def _build_start_message(self):
        return "Dang goi PP-StructureV3 pipeline rieng..."

    def _build_completion_message(self, block_count, avg_confidence, elapsed_seconds):
        return (
            f"PP-StructureV3 doc duoc {block_count} khoi "
            f"(Tin cay: {avg_confidence:.1%}) trong {elapsed_seconds:.2f}s"
        )

    def _build_result_summary(self, data):
        return {
            "page_count": len(data.get("pages", []) or []),
            "avg_confidence": float(data.get("avg_confidence") or 0.0),
            "raw_text": data.get("raw_text") or "",
        }

    def _resolve_python_exe(self):
        if os.path.exists(self.python_exe):
            return self.python_exe
        if os.path.exists(sys.executable):
            return sys.executable
        raise RuntimeError("Moi truong OCR chua duoc cai dat. Hay chay Setup_Moi_Truong.bat.")

    def _build_subprocess_env(self, base_env=None):
        sub_env = dict(base_env or os.environ)
        sub_env.pop("PYTHONHOME", None)
        sub_env.pop("PYTHONPATH", None)
        return sub_env

    def _build_popen_kwargs(self, stderr_target):
        startupinfo = None
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": stderr_target,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "env": self._build_subprocess_env(),
        }
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["startupinfo"] = startupinfo
        return kwargs

    def _write_temp_image_if_needed(self, image_input):
        if isinstance(image_input, str):
            return image_input, False

        import cv2

        fd, image_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        if not cv2.imwrite(image_path, image_input):
            try:
                os.remove(image_path)
            except OSError:
                pass
            raise RuntimeError("Khong the tao file anh tam cho PP-StructureV3.")
        return image_path, True

    def extract_structure(self, image_input, stop_event=None, status_callback=None):
        if not os.path.exists(self.runner_script):
            raise RuntimeError("Khong tim thay ocr_structure_runner.py.")

        if status_callback:
            status_callback(self._build_start_message())

        image_path, is_temp_image = self._write_temp_image_if_needed(image_input)
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        started_at = time.perf_counter()
        proc = None
        stderr_fd, stderr_path = tempfile.mkstemp(suffix=".stderr.txt")
        os.close(stderr_fd)
        try:
            with open(stderr_path, "w", encoding="utf-8", errors="replace") as stderr_file:
                proc = subprocess.Popen(
                    [self._resolve_python_exe(), self.runner_script, image_path, output_path],
                    **self._build_popen_kwargs(stderr_file),
                )

                while proc.poll() is None:
                    if stop_event and stop_event.is_set():
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        raise EngineCancellationError("PP-StructureV3 cancelled")
                    if time.perf_counter() - started_at > self.subprocess_timeout_seconds:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        raise RuntimeError(
                            f"PP-StructureV3 timed out after {self.subprocess_timeout_seconds}s."
                        )
                    time.sleep(0.1)

                proc.wait()
            with open(stderr_path, "r", encoding="utf-8", errors="replace") as err_file:
                stderr = err_file.read()
            if proc.returncode != 0:
                details = (stderr or "").strip()
                raise RuntimeError(details or "PP-StructureV3 runner failed.")

            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            elapsed = float(data.get("elapsed_seconds") or (time.perf_counter() - started_at))
            if status_callback:
                summary = self._build_result_summary(data)
                status_callback(
                    self._build_completion_message(
                        block_count=len(data.get("pages", []) or []),
                        avg_confidence=summary["avg_confidence"],
                        elapsed_seconds=elapsed,
                    )
                )
            return data
        finally:
            if proc and proc.poll() is None:
                proc.kill()
            for path, should_remove in [(output_path, True), (image_path, is_temp_image)]:
                if should_remove:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            try:
                os.remove(stderr_path)
            except OSError:
                pass


_structure_engine = None


def get_structure_paddle_engine():
    global _structure_engine
    if _structure_engine is None:
        _structure_engine = StructurePaddleOCREngine()
    return _structure_engine
