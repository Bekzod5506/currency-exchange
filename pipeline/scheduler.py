import argparse
import time                                                    
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler   
from apscheduler.triggers.cron import CronTrigger

from pipeline import config
from pipeline.logger import get_logger
from pipeline.run_pipeline import main as run_pipeline_main

logger = get_logger(__name__)

JOB_ID = "daily_currency_pipeline"


def daily_job() -> None:
    logger.info("Scheduled run triggered")
    try:
        exit_code = run_pipeline_main([])
    except Exception:
        logger.exception("Scheduled run crashed")
        return

    if exit_code != 0:
        logger.error("Scheduled run finished with failures (exit code %d)", exit_code)
    else:
        logger.info("Scheduled run completed successfully")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the currency pipeline daily on a schedule")
    parser.add_argument(
        "--run-now", action="store_true",
        help="Run the pipeline once immediately, then keep the daily schedule",
    )
    args = parser.parse_args()

    tz = ZoneInfo(config.SCHEDULE_TIMEZONE)
    trigger = CronTrigger(
        hour=config.SCHEDULE_HOUR,
        minute=config.SCHEDULE_MINUTE,
        timezone=tz,
    )

    scheduler = BackgroundScheduler(timezone=tz)               
    scheduler.add_job(
        daily_job,
        trigger,
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    if (config.SCHEDULE_HOUR, config.SCHEDULE_MINUTE) > (8, 0):
        logger.warning(
            "Schedule %02d:%02d is after the 08:00 deadline in %s",
            config.SCHEDULE_HOUR, config.SCHEDULE_MINUTE, config.SCHEDULE_TIMEZONE,
        )

    if args.run_now:
        daily_job()

    next_run = trigger.get_next_fire_time(None, datetime.now(tz))
    logger.info(
        "Scheduler started: daily at %02d:%02d %s | next run: %s | press Ctrl+C to stop",
        config.SCHEDULE_HOUR, config.SCHEDULE_MINUTE, config.SCHEDULE_TIMEZONE, next_run,
    )

    scheduler.start()                                          
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()