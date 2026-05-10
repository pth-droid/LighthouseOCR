import time
import threading

class EngineCancellationError(Exception):
    """Raised when the process is cleanly aborted via a stop_event by the user."""
    pass

class RateLimiter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RateLimiter, cls).__new__(cls)
                cls._instance.last_flash_call_time = 0
                cls._instance.last_pro_call_time = 0
                cls._instance._flash_lock = threading.Lock()
                cls._instance._pro_lock = threading.Lock()
        return cls._instance

    def wait_if_needed(self, bucket_key: str, stop_event=None, status_callback=None):
        is_pro = "pro" in bucket_key.lower()
        lock = self._pro_lock if is_pro else self._flash_lock

        with lock:
            now = time.time()
            if is_pro:
                elapsed = now - self.last_pro_call_time
                required = 32.0  # Safe delay for 2 RPM Pro limit
            else:
                elapsed = now - self.last_flash_call_time
                required = 4.0   # Safe delay for 15 RPM Flash limit
            wait_time = max(0.0, required - elapsed)
            # Reserve the slot before releasing the lock — prevents a second thread
            # from reading the same stale timestamp and computing the same wait_time.
            reserved_time = now + wait_time
            if is_pro:
                self.last_pro_call_time = reserved_time
            else:
                self.last_flash_call_time = reserved_time

        if wait_time > 0:
            if wait_time > 2 and status_callback:
                status_callback(f"⏳ Hệ thống đang đợi LLM tự động ({int(wait_time)}s) để tránh 429 Rate Limit...")
            if stop_event:
                if stop_event.wait(wait_time):
                    raise EngineCancellationError("STOP_REQUESTED")
            else:
                time.sleep(wait_time)

global_rate_limiter = RateLimiter()
