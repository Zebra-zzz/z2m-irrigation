from __future__ import annotations

import logging
from pathlib import Path
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.components.frontend import add_extra_js_url

from .const import (
    DOMAIN,
    CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC,
    CONF_MANUAL_TOPICS,
    CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE,
    PLATFORMS,
    # v4.0-alpha-1 — new config keys
    CONF_WEATHER_VPD_ENTITY,
    CONF_WEATHER_RAIN_TODAY_ENTITY,
    CONF_WEATHER_RAIN_FORECAST_24H_ENTITY,
    CONF_WEATHER_TEMP_ENTITY,
    CONF_KILL_SWITCH_ENTITY,
    CONF_KILL_SWITCH_MODE,
    CONF_GLOBAL_SKIP_RAIN_MM,
    CONF_GLOBAL_SKIP_FORECAST_MM,
    CONF_GLOBAL_MIN_RUN_LITERS,
    DEFAULT_KILL_SWITCH_MODE,
    DEFAULT_GLOBAL_SKIP_RAIN_MM,
    DEFAULT_GLOBAL_SKIP_FORECAST_MM,
    DEFAULT_GLOBAL_MIN_RUN_LITERS,
    sig_zone_config_changed,
    SCHEDULE_MODES,
    SCHEDULE_MODE_SMART,
    SCHEDULE_MODE_FIXED,
    DAYS_OF_WEEK,
)
from .manager import ValveManager
from .zone_store import ZoneStore

_LOGGER = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Service names
#
# Schedule CRUD services were stubs in v3.x (they logged "disabled in v3.0.0"
# and did nothing). They are intentionally NOT registered in v4.0-alpha-1.
# Alpha-2 will reintroduce them backed by the real ScheduleEngine.
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_START_TIMED = "start_timed"
SERVICE_START_LITERS = "start_liters"
SERVICE_RESET_TOTALS = "reset_totals"
SERVICE_RESCAN = "rescan"
SERVICE_CLEAR_PANIC = "clear_panic"

# v4.0-alpha-1 — per-zone config services. The dashboard / Setup tab calls
# these to mutate stored zone config without re-running the config flow.
SERVICE_SET_ZONE_FACTOR = "set_zone_factor"
SERVICE_SET_ZONE_L_PER_MM = "set_zone_l_per_mm"
SERVICE_SET_ZONE_BASE_MM = "set_zone_base_mm"
SERVICE_SET_ZONE_IN_SMART_CYCLE = "set_zone_in_smart_cycle"
SERVICE_SET_ZONE_SKIP_THRESHOLDS = "set_zone_skip_thresholds"
SERVICE_RECALCULATE_NOW = "recalculate_now"

# v4.0-alpha-2 — schedule CRUD + run-now + skip-today services
SERVICE_CREATE_SCHEDULE = "create_schedule"
SERVICE_UPDATE_SCHEDULE = "update_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
SERVICE_ENABLE_SCHEDULE = "enable_schedule"
SERVICE_DISABLE_SCHEDULE = "disable_schedule"
SERVICE_RUN_SCHEDULE_NOW = "run_schedule_now"
SERVICE_RUN_SMART_NOW = "run_smart_now"
SERVICE_SKIP_TODAY = "skip_today"
SERVICE_CLEAR_SKIP_TODAY = "clear_skip_today"
SERVICE_CANCEL_QUEUE = "cancel_queue"

# v4.0-alpha-3 — reset a single zone's stored config back to defaults
SERVICE_RESET_ZONE_TO_DEFAULTS = "reset_zone_to_defaults"

SCHEMA_START_TIMED = vol.Schema({
    vol.Required("valve"): cv.string,
    vol.Required("minutes"): vol.Coerce(float),
})
SCHEMA_START_LITERS = vol.Schema({
    vol.Required("valve"): cv.string,
    vol.Required("liters"): vol.Coerce(float),
})
SCHEMA_RESET_TOTALS = vol.Schema({vol.Optional("valve"): cv.string})
SCHEMA_CLEAR_PANIC = vol.Schema({vol.Optional("cleared_by"): cv.string})

SCHEMA_SET_ZONE_FACTOR = vol.Schema({
    vol.Required("zone"): cv.string,
    vol.Required("factor"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=10.0)),
})
SCHEMA_SET_ZONE_L_PER_MM = vol.Schema({
    vol.Required("zone"): cv.string,
    vol.Required("l_per_mm"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1000.0)),
})
SCHEMA_SET_ZONE_BASE_MM = vol.Schema({
    vol.Required("zone"): cv.string,
    vol.Required("base_mm"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=50.0)),
})
SCHEMA_SET_ZONE_IN_SMART_CYCLE = vol.Schema({
    vol.Required("zone"): cv.string,
    vol.Required("enabled"): cv.boolean,
})
SCHEMA_SET_ZONE_SKIP_THRESHOLDS = vol.Schema({
    vol.Required("zone"): cv.string,
    vol.Optional("rain_mm"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("forecast_mm"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("min_run_liters"): vol.Any(None, vol.Coerce(float)),
})

# v4.0-alpha-2 — schedule schemas
_TIME_RE = vol.Match(r"^\d{1,2}:\d{2}$")
_DAY_LIST = vol.All(cv.ensure_list, [vol.In(DAYS_OF_WEEK)])
_ZONE_LIST = vol.All(cv.ensure_list, [cv.string])

SCHEMA_CREATE_SCHEDULE = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("time"): _TIME_RE,
    vol.Optional("days", default=[]): _DAY_LIST,
    vol.Optional("mode", default=SCHEDULE_MODE_SMART): vol.In(SCHEDULE_MODES),
    vol.Optional("zones", default=[]): _ZONE_LIST,
    vol.Optional("fixed_liters_per_zone"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("enabled", default=True): cv.boolean,
})

SCHEMA_UPDATE_SCHEDULE = vol.Schema({
    vol.Required("schedule_id"): cv.string,
    vol.Optional("name"): cv.string,
    vol.Optional("time"): _TIME_RE,
    vol.Optional("days"): _DAY_LIST,
    vol.Optional("mode"): vol.In(SCHEDULE_MODES),
    vol.Optional("zones"): _ZONE_LIST,
    vol.Optional("fixed_liters_per_zone"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("enabled"): cv.boolean,
})

SCHEMA_SCHEDULE_ID_ONLY = vol.Schema({vol.Required("schedule_id"): cv.string})
SCHEMA_RUN_SMART_NOW = vol.Schema({vol.Optional("zones", default=[]): _ZONE_LIST})
SCHEMA_NONE = vol.Schema({})

# v4.0-alpha-3
SCHEMA_RESET_ZONE_TO_DEFAULTS = vol.Schema({vol.Required("zone"): cv.string})


# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-6 — auto-register the embed card frontend resource
#
# Ships the JS file under custom_components/z2m_irrigation/www/ and serves
# it from a static path so any Lovelace dashboard can use:
#
#   type: custom:z2m-irrigation-embed-card
#
# without manual resource registration. The static path is registered
# once globally (not per-config-entry) so even if the integration is
# torn down and re-set-up the resource stays available.
#
# We try the modern async API first; if HA is too old, fall back to the
# sync register_static_path. Both are safe to call multiple times.
# ─────────────────────────────────────────────────────────────────────────────

_FRONTEND_REGISTERED = False
_FRONTEND_URL_BASE = "/z2m_irrigation_static"

# v4.0-rc-1 — list of frontend resources to ship. Each entry is a
# (filename, log_label) tuple. Add new cards here and they'll be
# auto-registered alongside the embed card.
_FRONTEND_RESOURCES: list[tuple[str, str]] = [
    ("z2m-irrigation-embed-card.js", "embed card"),
    ("z2m-irrigation-schedule-editor-card.js", "schedule editor card"),
]


async def _register_frontend_once(hass: HomeAssistant) -> None:
    """Register all integration JS files as static frontend resources.

    Idempotent across config entries via a module-level flag. Each
    resource is registered as a static path AND added to the frontend
    extra-JS list so the custom element auto-loads in every dashboard.

    Tries the modern async API first; falls back to the older sync
    helper for HA < 2024.7. Missing-file detection logs a warning but
    doesn't crash setup — the integration's entities and services are
    unaffected if the frontend cards can't be served.
    """
    global _FRONTEND_REGISTERED
    if _FRONTEND_REGISTERED:
        return

    pkg_www = Path(__file__).parent / "www"
    if not pkg_www.is_dir():
        _LOGGER.warning("Embed card www/ dir not found at %s", pkg_www)
        return

    # Collect (url, fs_path, label) for everything that exists.
    to_register: list[tuple[str, str, str]] = []
    for filename, label in _FRONTEND_RESOURCES:
        js_path = pkg_www / filename
        if not js_path.exists():
            _LOGGER.warning(
                "Frontend resource %s not found at %s; the corresponding "
                "card will not be available", filename, js_path,
            )
            continue
        url = f"{_FRONTEND_URL_BASE}/{filename}"
        to_register.append((url, str(js_path), label))

    if not to_register:
        return

    # Try the modern async API; bail out to sync fallback on any error.
    try:
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths([
            StaticPathConfig(url, fs_path, False)
            for (url, fs_path, _label) in to_register
        ])
    except Exception:
        for (url, fs_path, _label) in to_register:
            try:
                hass.http.register_static_path(url, fs_path, False)
            except Exception as e:
                _LOGGER.warning("Failed to register static path %s: %s", url, e)

    for (url, _fs_path, label) in to_register:
        try:
            add_extra_js_url(hass, url)
            _LOGGER.info("🎨 Registered %s: %s", label, url)
        except Exception as e:
            _LOGGER.warning("Failed to register extra JS URL %s: %s", url, e)

    _FRONTEND_REGISTERED = True


def _apply_options_to_manager(mgr: ValveManager, options) -> None:
    """Push weather entity ids + global thresholds onto the manager.

    Called both at setup time and from the options-update listener so that
    edits to the options flow are picked up live without an HA restart.
    """
    from .const import (
        DEFAULT_GLOBAL_SKIP_RAIN_MM,
        DEFAULT_GLOBAL_SKIP_FORECAST_MM,
        DEFAULT_GLOBAL_MIN_RUN_LITERS,
    )
    mgr.weather_vpd_entity = options.get(CONF_WEATHER_VPD_ENTITY) or None
    mgr.weather_rain_today_entity = options.get(CONF_WEATHER_RAIN_TODAY_ENTITY) or None
    mgr.weather_rain_forecast_24h_entity = options.get(CONF_WEATHER_RAIN_FORECAST_24H_ENTITY) or None
    mgr.weather_temp_entity = options.get(CONF_WEATHER_TEMP_ENTITY) or None
    mgr.global_skip_rain_threshold_mm = float(
        options.get(CONF_GLOBAL_SKIP_RAIN_MM, DEFAULT_GLOBAL_SKIP_RAIN_MM)
    )
    mgr.global_skip_forecast_threshold_mm = float(
        options.get(CONF_GLOBAL_SKIP_FORECAST_MM, DEFAULT_GLOBAL_SKIP_FORECAST_MM)
    )
    mgr.global_min_run_liters = float(
        options.get(CONF_GLOBAL_MIN_RUN_LITERS, DEFAULT_GLOBAL_MIN_RUN_LITERS)
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # v4.0-alpha-6 — register the embed card frontend resource so any
    # Lovelace dashboard can use `custom:z2m-irrigation-embed-card`
    # without manual resource setup. Idempotent across config entries.
    await _register_frontend_once(hass)

    # ─────────────────────────────────────────────────────────────────────
    # v4.0-alpha-1 — load the JSON config store before the manager starts.
    # The manager seeds zone defaults inside `_ensure_valve`, which needs
    # the store to already be loaded.
    # ─────────────────────────────────────────────────────────────────────
    zone_store = ZoneStore(hass, entry.entry_id)
    await zone_store.async_load()

    base = entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    manual = [
        s.strip()
        for s in (entry.options.get(CONF_MANUAL_TOPICS, "") or "").splitlines()
        if s.strip()
    ]
    flow_scale = float(entry.options.get(CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE))

    # v4.0-alpha-1 — read new config flow options (all optional).
    kill_switch_entity = entry.options.get(CONF_KILL_SWITCH_ENTITY) or None
    kill_switch_mode = entry.options.get(CONF_KILL_SWITCH_MODE, DEFAULT_KILL_SWITCH_MODE)

    mgr = ValveManager(
        hass,
        base,
        manual,
        flow_scale,
        zone_store=zone_store,
        kill_switch_entity=kill_switch_entity,
        kill_switch_mode=kill_switch_mode,
    )

    # v4.0-alpha-1 — push weather entities + global thresholds onto the
    # manager so the calculator can read them. These live as plain
    # attributes (not constructor params) because they're frequently edited
    # at runtime via the options flow.
    _apply_options_to_manager(mgr, entry.options)

    hass.data[DOMAIN][entry.entry_id] = {
        "manager": mgr,
        "zone_store": zone_store,
    }

    # ─────────────────────────────────────────────────────────────────────
    # Service handlers
    # ─────────────────────────────────────────────────────────────────────

    async def _start_timed(call):
        mgr.start_timed(call.data["valve"], call.data["minutes"])

    async def _start_liters(call):
        mgr.start_liters(call.data["valve"], call.data["liters"])

    async def _reset_totals(call):
        mgr.reset_totals(call.data.get("valve"))

    async def _rescan(call):
        await mgr.async_stop()
        await mgr.async_start()

    async def _clear_panic(call):
        cleared_by = call.data.get("cleared_by", "service_call")
        mgr.clear_panic(cleared_by=cleared_by)

    async def _set_zone_factor(call):
        await zone_store.update_zone(
            call.data["zone"], factor=float(call.data["factor"])
        )
        mgr._dispatch_signal(sig_zone_config_changed(call.data['zone']))
        await mgr.recalculate_today()

    async def _set_zone_l_per_mm(call):
        await zone_store.update_zone(
            call.data["zone"], l_per_mm=float(call.data["l_per_mm"])
        )
        mgr._dispatch_signal(sig_zone_config_changed(call.data['zone']))
        await mgr.recalculate_today()

    async def _set_zone_base_mm(call):
        await zone_store.update_zone(
            call.data["zone"], base_mm=float(call.data["base_mm"])
        )
        mgr._dispatch_signal(sig_zone_config_changed(call.data['zone']))
        await mgr.recalculate_today()

    async def _set_zone_in_smart_cycle(call):
        await zone_store.update_zone(
            call.data["zone"], in_smart_cycle=bool(call.data["enabled"])
        )
        mgr._dispatch_signal(sig_zone_config_changed(call.data['zone']))
        await mgr.recalculate_today()

    async def _recalculate_now(call):
        """Force an immediate calculator refresh.

        Useful when the user has just edited zone config or weather sensors
        and wants the dashboard to reflect the new numbers without waiting
        for the 15-min periodic refresh.
        """
        await mgr.recalculate_today()

    async def _set_zone_skip_thresholds(call):
        patch = {}
        if "rain_mm" in call.data:
            patch["skip_rain_threshold_mm"] = call.data["rain_mm"]
        if "forecast_mm" in call.data:
            patch["skip_forecast_threshold_mm"] = call.data["forecast_mm"]
        if "min_run_liters" in call.data:
            patch["min_run_liters"] = call.data["min_run_liters"]
        if patch:
            await zone_store.update_zone(call.data["zone"], **patch)
            mgr._dispatch_signal(sig_zone_config_changed(call.data['zone']))
            await mgr.recalculate_today()

    hass.services.async_register(DOMAIN, SERVICE_START_TIMED, _start_timed, SCHEMA_START_TIMED)
    hass.services.async_register(DOMAIN, SERVICE_START_LITERS, _start_liters, SCHEMA_START_LITERS)
    hass.services.async_register(DOMAIN, SERVICE_RESET_TOTALS, _reset_totals, SCHEMA_RESET_TOTALS)
    hass.services.async_register(DOMAIN, SERVICE_RESCAN, _rescan)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_PANIC, _clear_panic, SCHEMA_CLEAR_PANIC)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_FACTOR, _set_zone_factor, SCHEMA_SET_ZONE_FACTOR,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_L_PER_MM, _set_zone_l_per_mm, SCHEMA_SET_ZONE_L_PER_MM,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_BASE_MM, _set_zone_base_mm, SCHEMA_SET_ZONE_BASE_MM,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_IN_SMART_CYCLE, _set_zone_in_smart_cycle,
        SCHEMA_SET_ZONE_IN_SMART_CYCLE,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ZONE_SKIP_THRESHOLDS, _set_zone_skip_thresholds,
        SCHEMA_SET_ZONE_SKIP_THRESHOLDS,
    )
    hass.services.async_register(DOMAIN, SERVICE_RECALCULATE_NOW, _recalculate_now)

    # ─────────────────────────────────────────────────────────────────────
    # v4.0-alpha-2 — schedule services
    #
    # All gated on the engine being available. The engine is only created
    # when the integration was set up via v4.0+ (i.e. `zone_store` is
    # present), so on a fresh install these always work; on a hypothetical
    # downgrade-then-upgrade with stale hass.data they degrade to a clear
    # error log instead of crashing.
    # ─────────────────────────────────────────────────────────────────────

    def _engine():
        eng = mgr.schedule_engine
        if eng is None:
            _LOGGER.error(
                "Schedule engine is not available — schedule services are disabled"
            )
        return eng

    async def _create_schedule(call):
        await zone_store.create_schedule(
            name=call.data["name"],
            time=call.data["time"],
            days=call.data.get("days", []) or [],
            mode=call.data.get("mode", SCHEDULE_MODE_SMART),
            zones=call.data.get("zones", []) or [],
            fixed_liters_per_zone=call.data.get("fixed_liters_per_zone"),
            enabled=call.data.get("enabled", True),
        )
        mgr._notify_global()

    async def _update_schedule(call):
        sid = call.data["schedule_id"]
        patch = {k: v for k, v in call.data.items() if k != "schedule_id"}
        await zone_store.update_schedule(sid, **patch)
        mgr._notify_global()

    async def _delete_schedule(call):
        await zone_store.delete_schedule(call.data["schedule_id"])
        mgr._notify_global()

    async def _enable_schedule(call):
        await zone_store.update_schedule(call.data["schedule_id"], enabled=True)
        mgr._notify_global()

    async def _disable_schedule(call):
        await zone_store.update_schedule(call.data["schedule_id"], enabled=False)
        mgr._notify_global()

    async def _run_schedule_now(call):
        eng = _engine()
        if eng is None:
            return
        await eng.run_schedule_now(call.data["schedule_id"])

    async def _run_smart_now(call):
        eng = _engine()
        if eng is None:
            return
        await eng.run_smart_now(zones=call.data.get("zones") or None)

    async def _skip_today(call):
        eng = _engine()
        if eng is None:
            return
        eng.set_skip_today(True)

    async def _clear_skip_today(call):
        eng = _engine()
        if eng is None:
            return
        eng.set_skip_today(False)

    async def _cancel_queue(call):
        eng = _engine()
        if eng is None:
            return
        eng.cancel_all()
        mgr._notify_global()

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_SCHEDULE, _create_schedule, SCHEMA_CREATE_SCHEDULE,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_SCHEDULE, _update_schedule, SCHEMA_UPDATE_SCHEDULE,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_SCHEDULE, _delete_schedule, SCHEMA_SCHEDULE_ID_ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ENABLE_SCHEDULE, _enable_schedule, SCHEMA_SCHEDULE_ID_ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISABLE_SCHEDULE, _disable_schedule, SCHEMA_SCHEDULE_ID_ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_SCHEDULE_NOW, _run_schedule_now, SCHEMA_SCHEDULE_ID_ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_SMART_NOW, _run_smart_now, SCHEMA_RUN_SMART_NOW,
    )
    hass.services.async_register(DOMAIN, SERVICE_SKIP_TODAY, _skip_today, SCHEMA_NONE)
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_SKIP_TODAY, _clear_skip_today, SCHEMA_NONE,
    )
    hass.services.async_register(DOMAIN, SERVICE_CANCEL_QUEUE, _cancel_queue, SCHEMA_NONE)

    async def _reset_zone_to_defaults(call):
        zone = call.data["zone"]
        await zone_store.reset_zone_to_defaults(zone)
        mgr._dispatch_signal(sig_zone_config_changed(zone))
        await mgr.recalculate_today()

    hass.services.async_register(
        DOMAIN, SERVICE_RESET_ZONE_TO_DEFAULTS,
        _reset_zone_to_defaults, SCHEMA_RESET_ZONE_TO_DEFAULTS,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await mgr.async_start()

    async def _options_updated(hass: HomeAssistant, changed_entry: ConfigEntry) -> None:
        if changed_entry.entry_id != entry.entry_id:
            return
        await mgr.async_stop()
        mgr.base = changed_entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
        mgr.manual_topics = [
            s.strip()
            for s in (changed_entry.options.get(CONF_MANUAL_TOPICS, "") or "").splitlines()
            if s.strip()
        ]
        mgr.flow_scale = float(changed_entry.options.get(CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE))
        # v4.0-alpha-1 — also pick up safety/weather config changes live.
        mgr.kill_switch_entity = changed_entry.options.get(CONF_KILL_SWITCH_ENTITY) or None
        mgr.kill_switch_mode = changed_entry.options.get(
            CONF_KILL_SWITCH_MODE, DEFAULT_KILL_SWITCH_MODE,
        )
        _apply_options_to_manager(mgr, changed_entry.options)
        await mgr.async_start()
        # Refresh the calculator with the new weather entities / thresholds.
        await mgr.recalculate_today()

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN][entry.entry_id]
    mgr: ValveManager = data["manager"]
    await mgr.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
