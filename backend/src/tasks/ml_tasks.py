import time
import httpx
import dramatiq
from src.tasks.broker import broker  # noqa: F401
from src.core.configs import configs

@dramatiq.actor(max_retries=10, min_backoff=1000, max_backoff=8000, time_limit=60_000)
def start_ml_pipeline(group_uuid: str):
    ml_url  = configs.ml_pipeline.url.rstrip("/") + "/"
    callback = f"{configs.backend_base_url.rstrip('/')}{configs.ml_pipeline.callback_path_ocr}"
    params = {
        "source":  f"/out/var/data/groups/{group_uuid}/raw_data/",
        "dst":     f"/out/var/data/groups/{group_uuid}/process/",
        "callback": callback,
    }
    backoff = 0.5
    for attempt in range(6):
        try:
            with httpx.Client(timeout=10) as client:
                r = client.get(ml_url, params=params)
                r.raise_for_status()
                return
        except Exception:
            if attempt == 5:
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 8)
