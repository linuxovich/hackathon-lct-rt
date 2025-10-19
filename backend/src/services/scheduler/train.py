import asyncio
import time
import os
import shutil
from pathlib import Path
import sys
import httpx
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.configs import configs

logger.remove()
logger.add(sys.stdout, level="INFO", enqueue=True)

VAR_ROOT = Path(configs.dirs.store).resolve().parent
TRAIN_ROOT = VAR_ROOT / "train"
TRAIN_JSONS_DIR = TRAIN_ROOT / "texts"
TRAIN_IMAGES_DIR = TRAIN_ROOT / "images"

def _ensure_train_dirs() -> None:
    TRAIN_JSONS_DIR.mkdir(parents=True, exist_ok=True)
    TRAIN_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

async def model_train():
    _ensure_train_dirs()
    backoff = 0.5
    url = configs.ml_pipeline.training_url
    params = {'model': 'baseline', 
              'checkpoint_dir': '/ml/models/',
              'labels_dir': '/out/var/train/texts/', 
              'input_image_dir': '/out/var/train/images/'}
    for attempt in range(6):
        try:
            with httpx.Client(timeout=10) as client:
                logger.info('START MODEL TRAIN')
                r = client.get(url, params=params)
                r.raise_for_status()
                return
        except Exception:
            if attempt == 5:
                logger.info('FAILED TO TRAIN')
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 8)
        finally:
            shutil.rmtree('/out/var/train/')
            os.mkdir("/out/var/train/")
    return 1

async def main():
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(
        model_train,
        CronTrigger(day_of_week='sat', hour=9, minute=0),  # каждая суббота 09:00 UTC
        id="queue-refresh",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    sched.start()
    logger.info("scheduler started: every Saturday at 09:00 UTC")
    await asyncio.Event().wait()
if __name__ == "__main__":
    asyncio.run(main())

