"""Daily delivery aggregator.

v4.0-alpha-4 — pre-builds the per-day per-zone summaries that the
dashboard's Insight tab reads. This is a pure data-shaping module: the
inputs are the integration's existing SQLite session history (queried
via `IrrigationDatabase.get_daily_breakdown`) and the current set of
known valves; the output is a `DailySummary` snapshot the manager
caches and the new sensors render.

Why a separate cache (instead of querying the DB on every sensor read):

  * The dashboard cards re-render frequently (every state push) and a
    SQLite group-by over 30 days × N valves on every render would be
    wasteful.
  * The cache is small (~30 days × ~10 zones × ~50 bytes ≈ 15 KB) and
    refreshes cheaply (one query per valve, ~ms each).
  * Persisting the snapshot to the JSON ZoneStore means the dashboard
    has data the moment HA finishes loading, even before the first
    15-min refresh tick has run.

This module does no I/O directly — `build_daily_summary` is async only
because the database calls are. Pure-data helpers (`zero_fill`,
`sum_by_date`) are sync and unit-testable in isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import IrrigationDatabase

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data shapes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DayBucket:
    """One day of delivery for one zone (or for all zones combined)."""
    date: str           # ISO date "YYYY-MM-DD"
    liters: float
    minutes: float
    sessions: int


@dataclass
class ZoneSeries:
    """Time-series of daily buckets for one zone, most-recent first."""
    zone: str
    name: str
    days: List[DayBucket] = field(default_factory=list)

    @property
    def total_liters(self) -> float:
        return round(sum(d.liters for d in self.days), 2)

    @property
    def total_minutes(self) -> float:
        return round(sum(d.minutes for d in self.days), 2)

    @property
    def total_sessions(self) -> int:
        return sum(d.sessions for d in self.days)


@dataclass
class DailySummary:
    """Full snapshot — per-zone series + a global combined series."""
    days_back: int
    built_at: str               # ISO timestamp
    zones: List[ZoneSeries] = field(default_factory=list)
    combined: List[DayBucket] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable view used by ZoneStore persistence."""
        return {
            "days_back": self.days_back,
            "built_at": self.built_at,
            "zones": [
                {
                    "zone": z.zone,
                    "name": z.name,
                    "days": [asdict(d) for d in z.days],
                }
                for z in self.zones
            ],
            "combined": [asdict(d) for d in self.combined],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailySummary":
        """Inverse of to_dict — used to hydrate from the persisted snapshot."""
        zones = []
        for zd in data.get("zones", []):
            days = [DayBucket(**dd) for dd in zd.get("days", [])]
            zones.append(ZoneSeries(
                zone=zd.get("zone", ""),
                name=zd.get("name", zd.get("zone", "")),
                days=days,
            ))
        combined = [DayBucket(**dd) for dd in data.get("combined", [])]
        return cls(
            days_back=int(data.get("days_back", 30)),
            built_at=data.get("built_at", ""),
            zones=zones,
            combined=combined,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers (no I/O)
# ─────────────────────────────────────────────────────────────────────────────


def _date_str(d: date) -> str:
    return d.isoformat()


def zero_fill(rows: List[Dict[str, Any]], days_back: int) -> List[DayBucket]:
    """Convert a sparse list of rows from the SQL query into a dense
    contiguous date series, most-recent first, with zero-filled gaps.

    `rows` is the raw output of `IrrigationDatabase.get_daily_breakdown`
    — only days that had at least one session are present. The dashboard
    chart wants every date in the window so the bars line up.
    """
    by_date = {r["date"]: r for r in rows}
    today = datetime.now(timezone.utc).date()
    out: List[DayBucket] = []
    for offset in range(days_back):
        d = today - timedelta(days=offset)
        key = _date_str(d)
        r = by_date.get(key)
        if r is None:
            out.append(DayBucket(date=key, liters=0.0, minutes=0.0, sessions=0))
        else:
            out.append(DayBucket(
                date=key,
                liters=float(r.get("liters", 0)),
                minutes=float(r.get("minutes", 0)),
                sessions=int(r.get("sessions", 0)),
            ))
    return out


def sum_by_date(zone_series: List[ZoneSeries]) -> List[DayBucket]:
    """Combine per-zone series into a single across-all-zones series.

    Iterates each zone's days, accumulating into a per-date bucket. The
    output is in the same date order as the input series (most-recent
    first), one entry per unique date observed.
    """
    by_date: Dict[str, DayBucket] = {}
    for zs in zone_series:
        for db in zs.days:
            agg = by_date.get(db.date)
            if agg is None:
                by_date[db.date] = DayBucket(
                    date=db.date,
                    liters=db.liters,
                    minutes=db.minutes,
                    sessions=db.sessions,
                )
            else:
                agg.liters = round(agg.liters + db.liters, 2)
                agg.minutes = round(agg.minutes + db.minutes, 2)
                agg.sessions += db.sessions
    # Most-recent first
    return sorted(by_date.values(), key=lambda x: x.date, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Builder — does I/O via the database
# ─────────────────────────────────────────────────────────────────────────────


async def build_daily_summary(
    db: IrrigationDatabase,
    valves: Dict[str, Any],
    *,
    days_back: int = 30,
    local_tz: Optional[Any] = None,
) -> DailySummary:
    """Query the SQLite db once per valve, zero-fill, and combine.

    `valves` is `ValveManager.valves` (mapping of friendly_name → Valve).
    We pass it as a generic dict so this module doesn't have to import
    the Valve dataclass and create a circular dependency.

    `local_tz` (v4.0-rc-3 hotfix): if provided, the daily breakdown bins
    sessions by LOCAL-time date instead of UTC date. Without this, an
    Insight tab chart in Melbourne would attribute a session that ran
    at 22:00 local (= 12:00 UTC) to the previous day. The manager
    passes `dt_util.DEFAULT_TIME_ZONE` (HA's configured local TZ).
    """
    zone_series: List[ZoneSeries] = []
    for topic, v in valves.items():
        try:
            rows = await db.get_daily_breakdown(
                topic, days=days_back, local_tz=local_tz,
            )
        except Exception as e:
            _LOGGER.warning(
                "Aggregator: get_daily_breakdown(%s) failed: %s", topic, e,
            )
            rows = []
        zone_series.append(ZoneSeries(
            zone=topic,
            name=getattr(v, "name", topic),
            days=zero_fill(rows, days_back),
        ))

    combined = sum_by_date(zone_series)

    summary = DailySummary(
        days_back=days_back,
        built_at=datetime.now(timezone.utc).isoformat(),
        zones=zone_series,
        combined=combined,
    )
    _LOGGER.debug(
        "📊 Aggregator: built %d-day summary across %d zones, %.2f L total",
        days_back, len(zone_series),
        sum(zs.total_liters for zs in zone_series),
    )
    return summary
