import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import atexit

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
        self.use_persistent_worker = os.environ.get("OCR_STRUCTURE_DISABLE_WORKER", "").strip() != "1"
        self._worker_proc = None
        self._worker_stderr_file = None
        self._worker_stderr_path = ""
        self._worker_job_seq = 0
        atexit.register(self.close)

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
        sub_env["PYTHONDONTWRITEBYTECODE"] = "1"
        return sub_env

    def _build_popen_kwargs(self, stderr_target, stdout_target=subprocess.DEVNULL, stdin_target=None):
        startupinfo = None
        kwargs = {
            "stdout": stdout_target,
            "stderr": stderr_target,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "env": self._build_subprocess_env(),
        }
        if stdin_target is not None:
            kwargs["stdin"] = stdin_target
            kwargs["bufsize"] = 1
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["startupinfo"] = startupinfo
        return kwargs

    def _build_worker_command(self):
        return [self._resolve_python_exe(), self.runner_script, "--worker"]

    def _build_worker_popen_kwargs(self, stderr_target):
        return self._build_popen_kwargs(
            stderr_target=stderr_target,
            stdout_target=subprocess.PIPE,
            stdin_target=subprocess.PIPE,
        )

    def _is_worker_alive(self):
        return self._worker_proc is not None and self._worker_proc.poll() is None

    def _read_worker_stderr(self):
        if not self._worker_stderr_path or not os.path.exists(self._worker_stderr_path):
            return ""
        try:
            with open(self._worker_stderr_path, "r", encoding="utf-8", errors="replace") as err_file:
                return err_file.read()
        except OSError:
            return ""

    def _start_worker(self):
        if self._is_worker_alive():
            return
        self.close()
        stderr_fd, stderr_path = tempfile.mkstemp(suffix=".structure-worker.stderr.txt")
        os.close(stderr_fd)
        self._worker_stderr_path = stderr_path
        self._worker_stderr_file = open(stderr_path, "w", encoding="utf-8", errors="replace")
        self._worker_proc = subprocess.Popen(
            self._build_worker_command(),
            **self._build_worker_popen_kwargs(self._worker_stderr_file),
        )

    def close(self):
        proc = self._worker_proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self._worker_proc = None
        if self._worker_stderr_file:
            try:
                self._worker_stderr_file.close()
            except OSError:
                pass
        self._worker_stderr_file = None
        if self._worker_stderr_path:
            try:
                os.remove(self._worker_stderr_path)
            except OSError:
                pass
        self._worker_stderr_path = ""

    def _terminate_worker_after_failure(self):
        proc = self._worker_proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._worker_proc = None

    def _read_worker_response_line(self, stop_event, started_at):
        proc = self._worker_proc
        response_queue = queue.Queue(maxsize=1)

        def _reader():
            try:
                response_queue.put(proc.stdout.readline())
            except Exception as exc:
                response_queue.put(exc)

        threading.Thread(target=_reader, daemon=True).start()
        while True:
            try:
                item = response_queue.get(timeout=0.1)
                if isinstance(item, Exception):
                    raise RuntimeError(f"PP-StructureV3 worker response read failed: {item}")
                return item
            except queue.Empty:
                if stop_event and stop_event.is_set():
                    self._terminate_worker_after_failure()
                    raise EngineCancellationError("PP-StructureV3 cancelled")
                if time.perf_counter() - started_at > self.subprocess_timeout_seconds:
                    self._terminate_worker_after_failure()
                    raise RuntimeError(f"PP-StructureV3 timed out after {self.subprocess_timeout_seconds}s.")
                if proc.poll() is not None:
                    try:
                        item = response_queue.get(timeout=0.5)
                        if item:
                            return item
                    except queue.Empty:
                        pass
                    stderr = self._read_worker_stderr().strip()
                    raise RuntimeError(stderr or f"PP-StructureV3 worker stopped with code {proc.returncode}.")

    def _run_worker_job(self, image_path, output_path, stop_event=None):
        self._start_worker()
        if not self._worker_proc or not self._worker_proc.stdin:
            raise RuntimeError("PP-StructureV3 worker did not start.")

        self._worker_job_seq += 1
        job_id = str(self._worker_job_seq)
        job = {
            "job_id": job_id,
            "image_path": image_path,
            "output_path": output_path,
        }
        started_at = time.perf_counter()
        try:
            self._worker_proc.stdin.write(json.dumps(job, ensure_ascii=False) + "\n")
            self._worker_proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            stderr = self._read_worker_stderr().strip()
            self._terminate_worker_after_failure()
            raise RuntimeError(stderr or f"PP-StructureV3 worker input failed: {exc}")

        line = self._read_worker_response_line(stop_event, started_at)
        if not line:
            stderr = self._read_worker_stderr().strip()
            self._terminate_worker_after_failure()
            raise RuntimeError(stderr or "PP-StructureV3 worker returned no response.")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            self._terminate_worker_after_failure()
            raise RuntimeError(f"PP-StructureV3 worker returned invalid response: {line.strip()} ({exc})")
        if response.get("job_id") not in (None, job_id):
            raise RuntimeError(f"PP-StructureV3 worker response mismatch: {response.get('job_id')} != {job_id}")
        if not response.get("ok"):
            error = response.get("error") or "PP-StructureV3 worker failed."
            details = response.get("traceback") or ""
            raise RuntimeError("\n".join(part for part in [error, details] if part))

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

    def _extract_structure_oneshot(self, image_path, output_path, stop_event, started_at):
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
        finally:
            if proc and proc.poll() is None:
                proc.kill()
            try:
                os.remove(stderr_path)
            except OSError:
                pass

    def extract_structure(self, image_input, stop_event=None, status_callback=None):
        if not os.path.exists(self.runner_script):
            raise RuntimeError("Khong tim thay ocr_structure_runner.py.")

        if status_callback:
            status_callback(self._build_start_message())

        image_path, is_temp_image = self._write_temp_image_if_needed(image_input)
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        started_at = time.perf_counter()
        try:
            if self.use_persistent_worker:
                if status_callback and not self._is_worker_alive():
                    status_callback(
                        "Dang nap PP-StructureV3 worker lan dau "
                        "(co the mat 20-90s tren may yeu)..."
                    )
                self._run_worker_job(image_path, output_path, stop_event=stop_event)
            else:
                self._extract_structure_oneshot(image_path, output_path, stop_event, started_at)

            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            elapsed = time.perf_counter() - started_at
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
            for path, should_remove in [(output_path, True), (image_path, is_temp_image)]:
                if should_remove:
                    try:
                        os.remove(path)
                    except OSError:
                        pass


_structure_engine = None


def get_structure_paddle_engine():
    global _structure_engine
    if _structure_engine is None:
        _structure_engine = StructurePaddleOCREngine()
    return _structure_engine
