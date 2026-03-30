import time
import threading

class RateLimiter:
    def __init__(self, rate_per_sec: int):
        self.interval = 1.0 / float(rate_per_sec)
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            sleep_for = self.interval - (now - self.last)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self.last = time.monotonic()
