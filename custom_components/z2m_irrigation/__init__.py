from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, CONF_MANUAL_TOPICS, CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE, PLATFORMS,
)
from .manager import ValveManager
# Scheduler temporarily disabled in v3.0.0 - awaiting local database migration
# from .scheduler import IrrigationScheduler

_LOGGER = logging.getLogger(__name__)

SERVICE_START_TIMED = "start_timed"
SERVICE_START_LITERS = "start_liters"
SERVICE_RESET_TOTALS = "reset_totals"
SERVICE_RESCAN = "rescan"
SERVICE_CREATE_SCHEDULE = "create_schedule"
SERVICE_UPDATE_SCHEDULE = "update_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
SERVICE_ENABLE_SCHEDULE = "enable_schedule"
SERVICE_DISABLE_SCHEDULE = "disable_schedule"
SERVICE_RUN_SCHEDULE = "run_schedule_now"
SERVICE_RELOAD_SCHEDULES = "reload_schedules"

SCHEMA_START_TIMED = vol.Schema({vol.Required("valve"): cv.string, vol.Required("minutes"): vol.Coerce(float)})
SCHEMA_START_LITERS = vol.Schema({vol.Required("valve"): cv.string, vol.Required("liters"): vol.Coerce(float)})
SCHEMA_RESET_TOTALS = vol.Schema({vol.Optional("valve"): cv.string})
SCHEMA_CREATE_SCHEDULE = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("valve"): cv.string,
    vol.Required("schedule_type"): vol.In(["time_based", "interval"]),
    vol.Optional("times"): [cv.string],
    vol.Optional("days_of_week"): [vol.Coerce(int)],
    vol.Optional("interval_hours"): vol.Coerce(int),
    vol.Required("run_type"): vol.In(["duration", "volume"]),
    vol.Required("run_value"): vol.Coerce(float),
    vol.Optional("conditions"): dict,
    vol.Optional("enabled"): cv.boolean,
})
SCHEMA_UPDATE_SCHEDULE = vol.Schema({
    vol.Required("schedule_id"): cv.string,
    vol.Optional("name"): cv.string,
    vol.Optional("valve"): cv.string,
    vol.Optional("schedule_type"): vol.In(["time_based", "interval"]),
    vol.Optional("times"): [cv.string],
    vol.Optional("days_of_week"): [vol.Coerce(int)],
    vol.Optional("interval_hours"): vol.Coerce(int),
    vol.Optional("run_type"): vol.In(["duration", "volume"]),
    vol.Optional("run_value"): vol.Coerce(float),
    vol.Optional("conditions"): dict,
    vol.Optional("enabled"): cv.boolean,
})
SCHEMA_DELETE_SCHEDULE = vol.Schema({vol.Required("schedule_id"): cv.string})
SCHEMA_ENABLE_SCHEDULE = vol.Schema({vol.Required("schedule_id"): cv.string})
SCHEMA_DISABLE_SCHEDULE = vol.Schema({vol.Required("schedule_id"): cv.string})
SCHEMA_RUN_SCHEDULE = vol.Schema({vol.Required("schedule_id"): cv.string})

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    base = entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    manual = [s.strip() for s in (entry.options.get(CONF_MANUAL_TOPICS, "") or "").splitlines() if s.strip()]
    flow_scale = float(entry.options.get(CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE))
    mgr = ValveManager(hass, base, manual, flow_scale)

    # Note: Scheduler is temporarily disabled in v3.0.0 pending local database migration
    # Core irrigation tracking works 100% locally with SQLite
    # Scheduler will be re-enabled with local SQLite storage in v3.1.0
    # Use Home Assistant automations for scheduling in the meantime
    scheduler = None

    hass.data[DOMAIN][entry.entry_id] = {"manager": mgr, "scheduler": scheduler}

    async def _start_timed(call):
        mgr.start_timed(call.data["valve"], call.data["minutes"])

    async def _start_liters(call):
        mgr.start_liters(call.data["valve"], call.data["liters"])

    async def _reset_totals(call):
        mgr.reset_totals(call.data.get("valve"))

    async def _rescan(call):
        await mgr.async_stop()
        await mgr.async_start()

    async def _create_schedule(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        data = dict(call.data)
        data["valve_topic"] = data.pop("valve")
        await scheduler.add_schedule(data)

    async def _update_schedule(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        schedule_id = call.data["schedule_id"]
        data = {k: v for k, v in call.data.items() if k != "schedule_id"}
        if "valve" in data:
            data["valve_topic"] = data.pop("valve")
        await scheduler.update_schedule(schedule_id, data)

    async def _delete_schedule(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        await scheduler.delete_schedule(call.data["schedule_id"])

    async def _enable_schedule(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        await scheduler.update_schedule(call.data["schedule_id"], {"enabled": True})

    async def _disable_schedule(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        await scheduler.update_schedule(call.data["schedule_id"], {"enabled": False})

    async def _run_schedule(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        await scheduler._execute_schedule(call.data["schedule_id"])

    async def _reload_schedules(call):
        if scheduler is None:
            _LOGGER.error("Scheduler is disabled in v3.0.0 (requires local database migration)")
            return
        await scheduler.reload_schedules()

    hass.services.async_register(DOMAIN, SERVICE_START_TIMED, _start_timed, SCHEMA_START_TIMED)
    hass.services.async_register(DOMAIN, SERVICE_START_LITERS, _start_liters, SCHEMA_START_LITERS)
    hass.services.async_register(DOMAIN, SERVICE_RESET_TOTALS, _reset_totals, SCHEMA_RESET_TOTALS)
    hass.services.async_register(DOMAIN, SERVICE_RESCAN, _rescan)
    hass.services.async_register(DOMAIN, SERVICE_CREATE_SCHEDULE, _create_schedule, SCHEMA_CREATE_SCHEDULE)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_SCHEDULE, _update_schedule, SCHEMA_UPDATE_SCHEDULE)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_SCHEDULE, _delete_schedule, SCHEMA_DELETE_SCHEDULE)
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_SCHEDULE, _enable_schedule, SCHEMA_ENABLE_SCHEDULE)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_SCHEDULE, _disable_schedule, SCHEMA_DISABLE_SCHEDULE)
    hass.services.async_register(DOMAIN, SERVICE_RUN_SCHEDULE, _run_schedule, SCHEMA_RUN_SCHEDULE)
    hass.services.async_register(DOMAIN, SERVICE_RELOAD_SCHEDULES, _reload_schedules)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await mgr.async_start()
    if scheduler is not None:
        await scheduler.async_start()
    else:
        _LOGGER.warning("⚠️  Scheduler disabled in v3.0.0 - core irrigation tracking works fully locally")

    async def _options_updated(hass: HomeAssistant, changed_entry: ConfigEntry) -> None:
        if changed_entry.entry_id != entry.entry_id:
            return
        await mgr.async_stop()
        mgr.base = changed_entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
        mgr.manual_topics = [s.strip() for s in (changed_entry.options.get(CONF_MANUAL_TOPICS, "") or "").splitlines() if s.strip()]
        mgr.flow_scale = float(changed_entry.options.get(CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE))
        await mgr.async_start()

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN][entry.entry_id]
    mgr: ValveManager = data["manager"]
    scheduler = data.get("scheduler")
    await mgr.async_stop()
    if scheduler is not None:
        await scheduler.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
