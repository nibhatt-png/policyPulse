"""HTTP GET with retries, shared by every ingest worker thread.

Congress.gov answers bursts of requests with 429 Too Many Requests. When any
thread is rate-limited, ALL threads pause (via a shared "resume at" time) so
the workers don't keep hammering the server while it is limiting us.
"""
import threading, time, httpx

MAX_ATTEMPTS = 6
BASE_DELAY   = 5     # seconds; doubles each attempt (5, 10, 20, 40, 80)
MAX_DELAY    = 300

_lock      = threading.Lock()
_resume_at = 0.0

def _wait_for_pause() -> None:
    while True:
        with _lock:
            delay = _resume_at - time.time()
        if delay <= 0:
            return
        time.sleep(delay)

def _pause_all(seconds: float) -> None:
    global _resume_at
    with _lock:
        _resume_at = max(_resume_at, time.time() + seconds)

def get(url: str, **kwargs) -> httpx.Response:
    kwargs.setdefault("timeout", 60)
    kwargs.setdefault("follow_redirects", True)
    for attempt in range(MAX_ATTEMPTS):
        _wait_for_pause()
        try:
            resp = httpx.get(url, **kwargs)
        except httpx.TransportError:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(min(BASE_DELAY * 2 ** attempt, MAX_DELAY))
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == MAX_ATTEMPTS - 1:
                resp.raise_for_status()
            retry_after = resp.headers.get("retry-after", "")
            delay = float(retry_after) if retry_after.isdigit() else BASE_DELAY * 2 ** attempt
            delay = min(delay, MAX_DELAY)
            if resp.status_code == 429:
                _pause_all(delay)
            else:
                time.sleep(delay)
            continue

        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")
