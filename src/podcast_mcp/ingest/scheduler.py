#!/usr/bin/env python3
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from podcast_mcp.config import settings


SYNC_MODULE = "podcast_mcp.ingest.rss"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def next_run_at(cron_expression: str, timezone: ZoneInfo) -> datetime:
    now = datetime.now(timezone)
    return croniter(cron_expression, now).get_next(datetime)


def run_sync() -> None:
    log("Starting scheduled RSS sync")
    started_at = time.monotonic()
    subprocess.run([sys.executable, "-m", SYNC_MODULE], check=True)
    log(f"Finished scheduled RSS sync in {time.monotonic() - started_at:.1f}s")


def main() -> int:
    cron_expression = settings.sync_cron
    timezone_name = settings.sync_timezone
    timezone = ZoneInfo(timezone_name)

    log(f"RSS sync scheduler started cron='{cron_expression}' timezone='{timezone_name}'")

    while True:
        run_at = next_run_at(cron_expression, timezone)
        sleep_seconds = max(0, (run_at - datetime.now(timezone)).total_seconds())
        log(f"Next RSS sync at {run_at.isoformat()}")
        time.sleep(sleep_seconds)

        try:
            run_sync()
        except subprocess.CalledProcessError as error:
            log(f"Scheduled RSS sync failed with exit code {error.returncode}")
        except Exception as error:
            log(f"Scheduled RSS sync failed: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
