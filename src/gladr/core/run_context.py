"""Run metadata shared across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "America/New_York"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_datetime: str

    @classmethod
    def now(cls, timezone_name: str = DEFAULT_TIMEZONE) -> "RunContext":
        current = datetime.now(ZoneInfo(timezone_name))
        return cls(
            run_id=current.strftime("%Y%m%d_%H%M%S"),
            run_datetime=current.isoformat(timespec="seconds"),
        )
