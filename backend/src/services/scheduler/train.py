import asyncio
import time
import os
import shutil
import sys
import httpx
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.core.configs import configs

logger.remove()
logger.add(sys.stdout, level="INFO", enqueue=True)

async def model_train():
    backoff = 0.5
    url = configs.ml_pipeline.training_url
    params = {'model': '', 
              'checkpoint_dir': '',
              'labels_dir': '', 
              'input_image_dir': ''}
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
            shutil.rmtree('/var/train/')
            os.mkdir("/var/train/")
    return 1

async def main():
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(model_train, IntervalTrigger(seconds=15),
                  id="queue-refresh", coalesce=True, max_instances=1, replace_existing=True)
    sched.start()
    logger.info("scheduler started, every {}s", 15)
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

