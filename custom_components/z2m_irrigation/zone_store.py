"""Per-zone configuration storage for the z2m_irrigation integration.

v4.0-alpha-1 — introduces a JSON-backed config store, separate from the
SQLite session-history database (`database.py`). The two stores have very
different shapes and access patterns:

  * `database.py` (SQLite) — append-mostly time-series of valve sessions,
    queried for 24h/7d/lifetime aggregates and orphan recovery.
  * `zone_store.py` (HA Store JSON) — small, mutable config: per-zone
    calculator inputs, per-zone skip thresholds, schedule definitions
    (alpha-2), run history events (alpha-4).

Schedules are not yet present in alpha-1; the schema reserves the keys so
that the migration path stays at version 1 when alpha-2 lands.

Storage location: `.storage/z2m_irrigation.<entry_id>` — per config entry,
so a hypothetical second instance of the integration would not collide.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORE_VERSION,
    STORE_KEY_PREFIX,
    DEFAULT_ZONE_FACTOR,
    DEFAULT_ZONE_L_PER_MM,
    DEFAULT_ZONE_BASE_MM,
    DEFAULT_ZONE_IN_SMART_CYCLE,
    HISTORY_RETENTION_DAYS,
    HISTORY_MAX_ENTRIES,
    SCHEDULE_MODE_SMART,
    SCHEDULE_MODE_FIXED,
    DAYS_OF_WEEK,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class Schedule:
    """A user-defined irrigation schedule.

    Identified by a short opaque id (`sch_<hex>`). Schedules are stored as
    plain dicts in the JSON store; this dataclass is the typed view used
    by the engine and services. `from_dict` is tolerant of unknown keys
    so a future schema can extend it without breaking older code.

    Field semantics:
      * `time` — local-time "HH:MM" string. The engine resolves it to the
        config-entry's HA timezone every fire-time evaluation.
      * `days` — list of weekday tokens from `DAYS_OF_WEEK`. Empty list
        means "every day" (matches the legacy "no day filter" behavior).
      * `mode` — `smart` (calculator-driven per-zone liters) or `fixed`
        (every zone in `zones` gets `fixed_liters_per_zone`).
      * `zones` — explicit valve friendly_name list. Empty list in smart
        mode means "all zones currently flagged in_smart_cycle".
      * `last_run_at` / `last_run_outcome` — set by the engine after each
        fire attempt; rendered on the schedule list in the dashboard.
    """
    id: str
    name: str
    enabled: bool = True
    time: str = "06:00"
    days: List[str] = field(default_factory=list)  # [] = every day
    mode: str = SCHEDULE_MODE_SMART
    zones: List[str] = field(default_factory=list)  # [] = all in_smart_cycle
    fixed_liters_per_zone: Optional[float] = None
    created_at: str = ""
    last_run_at: Optional[str] = None
    last_run_outcome: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Schedule":
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        # Backfill required fields if a malformed entry was loaded.
        filtered.setdefault("id", "")
        filtered.setdefault("name", "")
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _new_schedule_id() -> str:
    """Generate a short opaque schedule id. Not cryptographically meaningful."""
    return f"sch_{secrets.token_hex(8)}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ZoneConfig:
    """Per-zone calculator + display config.

    Threshold fields use `None` to mean "inherit from global". The
    calculator and skip-condition checks resolve null → global at read time.
    """

    factor: float = DEFAULT_ZONE_FACTOR
    l_per_mm: float = DEFAULT_ZONE_L_PER_MM
    base_mm: float = DEFAULT_ZONE_BASE_MM
    in_smart_cycle: bool = DEFAULT_ZONE_IN_SMART_CYCLE

    skip_rain_threshold_mm: Optional[float] = None
    skip_forecast_threshold_mm: Optional[float] = None
    min_run_liters: Optional[float] = None

    display_name: Optional[str] = None
    display_color: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZoneConfig":
        """Create a ZoneConfig from stored dict, tolerating unknown keys.

        Unknown keys are dropped silently — this lets a future schema add
        fields without crashing on downgrade.
        """
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class ZoneStore:
    """JSON-backed per-zone config store.

    The store is loaded once on integration setup, mutated in-memory by the
    config services, and persisted on every change. All reads are sync from
    the in-memory copy; only writes hit disk.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._store: Store = Store(
            hass,
            STORE_VERSION,
            f"{STORE_KEY_PREFIX}.{entry_id}",
        )
        self._data: Dict[str, Any] = {
            "version": STORE_VERSION,
            "zones": {},
            "schedules": [],         # populated in alpha-2
            "history": {},           # schedule timeline (alpha-3)
            "daily_summary": None,   # snapshot for cold-start hydration (alpha-4)
        }
        self._loaded = False

    # ─────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────

    async def async_load(self) -> None:
        """Load store from disk. Idempotent."""
        if self._loaded:
            return
        raw = await self._store.async_load()
        if raw is not None:
            # Tolerate partial/legacy schemas — fill in any missing top-level keys.
            self._data = {
                "version": raw.get("version", STORE_VERSION),
                "zones": raw.get("zones", {}) or {},
                "schedules": raw.get("schedules", []) or [],
                "history": raw.get("history", {}) or {},
                "daily_summary": raw.get("daily_summary"),  # may be None
            }
            _LOGGER.info(
                "📁 ZoneStore loaded: %d zone(s), %d schedule(s)",
                len(self._data["zones"]), len(self._data["schedules"]),
            )
        else:
            _LOGGER.info("📁 ZoneStore: no existing store, starting fresh")
        self._loaded = True

    async def _async_save(self) -> None:
        """Persist the in-memory state to disk."""
        await self._store.async_save(self._data)

    # ─────────────────────────────────────────────────────────────────────
    # Zone config — public API
    # ─────────────────────────────────────────────────────────────────────

    def has_zone(self, zone: str) -> bool:
        return zone in self._data["zones"]

    def get_zone(self, zone: str) -> ZoneConfig:
        """Return the zone's config, or defaults if not yet stored.

        Does NOT auto-create the zone — call `ensure_zone()` for that.
        """
        raw = self._data["zones"].get(zone)
        if raw is None:
            return ZoneConfig()
        return ZoneConfig.from_dict(raw)

    def all_zones(self) -> Dict[str, ZoneConfig]:
        return {
            name: ZoneConfig.from_dict(raw)
            for name, raw in self._data["zones"].items()
        }

    async def ensure_zone(self, zone: str) -> ZoneConfig:
        """Create a zone with default config if it doesn't exist yet.

        Called from `ValveManager._ensure_valve` so that every discovered
        valve gets a corresponding entry in the zone store on first sight.
        Returns the resolved ZoneConfig.
        """
        if zone not in self._data["zones"]:
            cfg = ZoneConfig()
            self._data["zones"][zone] = asdict(cfg)
            await self._async_save()
            _LOGGER.info(
                "📁 ZoneStore: seeded defaults for new zone '%s'", zone
            )
            return cfg
        return ZoneConfig.from_dict(self._data["zones"][zone])

    async def update_zone(self, zone: str, **fields: Any) -> ZoneConfig:
        """Patch-update a zone's config and persist.

        Unknown fields are silently dropped. Pass `None` for a threshold
        field to clear it back to "inherit global".
        """
        existing = self._data["zones"].get(zone) or asdict(ZoneConfig())
        known = set(ZoneConfig.__dataclass_fields__)
        for k, v in fields.items():
            if k in known:
                existing[k] = v
        self._data["zones"][zone] = existing
        await self._async_save()
        _LOGGER.debug(
            "📁 ZoneStore: updated zone '%s' fields=%s", zone, list(fields.keys())
        )
        return ZoneConfig.from_dict(existing)

    async def delete_zone(self, zone: str) -> bool:
        """Remove a zone from the store. Returns True if it existed."""
        if zone in self._data["zones"]:
            del self._data["zones"][zone]
            await self._async_save()
            _LOGGER.info("📁 ZoneStore: deleted zone '%s'", zone)
            return True
        return False

    async def reset_zone_to_defaults(self, zone: str) -> ZoneConfig:
        """Replace this zone's stored config with fresh defaults.

        Used by the `reset_zone_to_defaults` service. Does NOT touch the
        zone's session-history rows in the SQLite database — those are
        the long-term record and should never be wiped by a config edit.
        """
        cfg = ZoneConfig()
        self._data["zones"][zone] = asdict(cfg)
        await self._async_save()
        _LOGGER.info("📁 ZoneStore: reset zone '%s' to defaults", zone)
        return cfg

    # ─────────────────────────────────────────────────────────────────────
    # Schedules — v4.0-alpha-2
    # ─────────────────────────────────────────────────────────────────────

    def all_schedules(self) -> List[Dict[str, Any]]:
        """Return all stored schedules as plain dicts (for the sensor)."""
        return list(self._data["schedules"])

    def all_schedules_typed(self) -> List[Schedule]:
        """Return all stored schedules as `Schedule` objects (for the engine)."""
        return [Schedule.from_dict(s) for s in self._data["schedules"]]

    def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        for raw in self._data["schedules"]:
            if raw.get("id") == schedule_id:
                return Schedule.from_dict(raw)
        return None

    async def create_schedule(
        self,
        *,
        name: str,
        time: str,
        days: List[str],
        mode: str,
        zones: List[str],
        fixed_liters_per_zone: Optional[float] = None,
        enabled: bool = True,
    ) -> Schedule:
        """Append a new schedule and persist. Returns the created Schedule."""
        sch = Schedule(
            id=_new_schedule_id(),
            name=name,
            enabled=enabled,
            time=time,
            days=list(days or []),
            mode=mode,
            zones=list(zones or []),
            fixed_liters_per_zone=fixed_liters_per_zone,
            created_at=_now_iso(),
            last_run_at=None,
            last_run_outcome=None,
        )
        self._data["schedules"].append(sch.to_dict())
        await self._async_save()
        _LOGGER.info(
            "📅 ZoneStore: created schedule %s '%s' time=%s mode=%s zones=%s",
            sch.id, sch.name, sch.time, sch.mode, sch.zones,
        )
        return sch

    async def update_schedule(
        self, schedule_id: str, **fields: Any
    ) -> Optional[Schedule]:
        """Patch-update an existing schedule. No-op if not found."""
        known = set(Schedule.__dataclass_fields__) - {"id", "created_at"}
        for raw in self._data["schedules"]:
            if raw.get("id") == schedule_id:
                for k, v in fields.items():
                    if k in known:
                        raw[k] = v
                await self._async_save()
                _LOGGER.info(
                    "📅 ZoneStore: updated schedule %s fields=%s",
                    schedule_id, list(fields.keys()),
                )
                return Schedule.from_dict(raw)
        _LOGGER.warning("📅 ZoneStore: update_schedule: %s not found", schedule_id)
        return None

    async def delete_schedule(self, schedule_id: str) -> bool:
        """Remove a schedule by id. Returns True if it existed."""
        before = len(self._data["schedules"])
        self._data["schedules"] = [
            s for s in self._data["schedules"] if s.get("id") != schedule_id
        ]
        if len(self._data["schedules"]) == before:
            return False
        await self._async_save()
        _LOGGER.info("📅 ZoneStore: deleted schedule %s", schedule_id)
        return True

    async def mark_schedule_run(
        self,
        schedule_id: str,
        *,
        outcome: str,
        when_iso: Optional[str] = None,
    ) -> None:
        """Stamp last_run_at + last_run_outcome on a schedule.

        Called by the engine after every fire attempt (success, skip, or
        error). The dashboard's schedule list reads these to render the
        per-row "last fired … (outcome)" line.
        """
        when = when_iso or _now_iso()
        for raw in self._data["schedules"]:
            if raw.get("id") == schedule_id:
                raw["last_run_at"] = when
                raw["last_run_outcome"] = outcome
                await self._async_save()
                return

    # ─────────────────────────────────────────────────────────────────────
    # History — v4.0-alpha-3
    #
    # The `history` top-level slot stores two kinds of records, indexed
    # by namespace key:
    #
    #   "_schedule_events": [...]      # global timeline of schedule
    #                                    fires and skips with outcome
    #                                    + zones + total liters.
    #
    #   "<zone_friendly_name>": [...]  # per-zone session summaries
    #                                    (start, end, liters, trigger).
    #                                    Populated by alpha-4 — alpha-3
    #                                    only ships the global timeline.
    #
    # Both kinds of records are pruned on every write by
    # `_prune_history_namespace`: entries older than HISTORY_RETENTION_DAYS
    # are removed, and any namespace with more than HISTORY_MAX_ENTRIES
    # records is truncated to the most recent HISTORY_MAX_ENTRIES.
    # ─────────────────────────────────────────────────────────────────────

    _SCHEDULE_EVENTS_KEY = "_schedule_events"

    def _prune_history_namespace(self, key: str) -> None:
        """Drop entries older than the retention window AND cap by count.

        Tolerates malformed records (missing/invalid `at` timestamp) by
        keeping them — better to leak a little than to lose data on a
        parse error.
        """
        records = self._data["history"].get(key)
        if not records:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_RETENTION_DAYS)
        kept: List[Dict[str, Any]] = []
        for r in records:
            at_str = r.get("at")
            if not at_str:
                kept.append(r)
                continue
            try:
                at_dt = datetime.fromisoformat(at_str.replace("Z", "+00:00"))
                if at_dt >= cutoff:
                    kept.append(r)
            except Exception:
                kept.append(r)  # malformed, don't drop

        # Hard count cap — keep most recent.
        if len(kept) > HISTORY_MAX_ENTRIES:
            kept = kept[-HISTORY_MAX_ENTRIES:]

        self._data["history"][key] = kept

    async def record_schedule_event(
        self,
        *,
        kind: str,                              # "fired" | "skipped"
        schedule_id: Optional[str],
        schedule_name: Optional[str],
        outcome: str,                           # OUTCOME_RAN, OUTCOME_SKIPPED_*, ...
        mode: Optional[str] = None,
        trigger: Optional[str] = None,          # "scheduled"|"catchup"|"manual"
        zones: Optional[List[str]] = None,
        total_liters: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Append a schedule event to the global timeline and persist.

        The dashboard's Insight tab reads this list to render the "what
        happened in the last 7 days" timeline. Records are kept for
        HISTORY_RETENTION_DAYS days, capped at HISTORY_MAX_ENTRIES total.
        """
        record: Dict[str, Any] = {
            "at": _now_iso(),
            "kind": kind,
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "outcome": outcome,
            "mode": mode,
            "trigger": trigger,
            "zones": list(zones or []),
            "total_liters": (
                round(float(total_liters), 2)
                if total_liters is not None else None
            ),
        }
        bucket = self._data["history"].setdefault(self._SCHEDULE_EVENTS_KEY, [])
        bucket.append(record)
        self._prune_history_namespace(self._SCHEDULE_EVENTS_KEY)
        await self._async_save()
        _LOGGER.debug(
            "📜 ZoneStore: recorded schedule event kind=%s outcome=%s schedule=%s",
            kind, outcome, schedule_id,
        )
        return record

    def schedule_events(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return the global schedule timeline, most-recent-first.

        `limit` clamps the returned slice to N records. None returns the
        full retained set (capped by HISTORY_MAX_ENTRIES).
        """
        records = list(self._data["history"].get(self._SCHEDULE_EVENTS_KEY, []))
        records.reverse()
        if limit is not None:
            records = records[:limit]
        return records

    def history_for_zone(self, zone: str) -> List[Dict[str, Any]]:
        """Per-zone session summaries — populated by alpha-4. Empty until then."""
        return list(self._data["history"].get(zone, []))

    # ─────────────────────────────────────────────────────────────────────
    # Daily summary snapshot — v4.0-alpha-4
    #
    # Holds the most recent `aggregator.DailySummary.to_dict()` so the
    # dashboard charts have data the moment HA finishes loading, even
    # before the manager's first 15-min refresh tick. The manager hydrates
    # its in-memory cache from this on startup, then overwrites it on
    # every successful aggregator build.
    # ─────────────────────────────────────────────────────────────────────

    def get_daily_summary(self) -> Optional[Dict[str, Any]]:
        return self._data.get("daily_summary")

    async def set_daily_summary(self, snapshot: Optional[Dict[str, Any]]) -> None:
        self._data["daily_summary"] = snapshot
        await self._async_save()
