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
        return cls._instance

    def wait_if_needed(self, bucket_key: str, stop_event=None, status_callback=None):
        with self._lock:  # Thread safe check and lock update
            now = time.time()
            if "pro" in bucket_key.lower():
                elapsed = now - self.last_pro_call_time
                required = 32.0  # Safe delay for 2 RPM Pro limit
            else:
                elapsed = now - self.last_flash_call_time
                required = 4.0   # Safe delay for 15 RPM Flash limit

            if elapsed < required:
                wait_time = required - elapsed
                if wait_time > 2 and status_callback:
                    status_callback(f"⏳ Hệ thống đang đợi LLM tự động ({int(wait_time)}s) để tránh 429 Rate Limit...")
                
                if stop_event:
                    if stop_event.wait(wait_time):
                        raise EngineCancellationError("STOP_REQUESTED")
                else:
                    time.sleep(wait_time)
            
            # Recalculate time after sleep
            if "pro" in bucket_key.lower():
                self.last_pro_call_time = time.time()
            else:
                self.last_flash_call_time = time.time()

global_rate_limiter = RateLimiter()
