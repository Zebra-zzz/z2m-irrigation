"""WebSocket API for Z2M Irrigation."""
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_register_websocket_handlers(hass: HomeAssistant):
    """Register WebSocket API handlers."""
    websocket_api.async_register_command(hass, handle_list_sessions)
    websocket_api.async_register_command(hass, handle_delete_session)
    websocket_api.async_register_command(hass, handle_clear_sessions)
    websocket_api.async_register_command(hass, handle_list_schedules)
    websocket_api.async_register_command(hass, handle_get_schedule)
    websocket_api.async_register_command(hass, handle_list_schedule_runs)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "z2m_irrigation/sessions/list",
        vol.Optional("valve_filter"): str,
        vol.Optional("start_date"): str,
        vol.Optional("end_date"): str,
    }
)
@websocket_api.async_response
async def handle_list_sessions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
):
    """Handle list sessions command."""
    valve_filter = msg.get("valve_filter")
    start_date = msg.get("start_date")
    end_date = msg.get("end_date")

    all_sessions = []
    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict) and "manager" in data:
            sessions = data["manager"].get_sessions(valve_filter, start_date, end_date)
            all_sessions.extend(sessions)

    all_sessions.sort(key=lambda x: x["start"], reverse=True)

    connection.send_result(msg["id"], {"sessions": all_sessions})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "z2m_irrigation/sessions/delete",
        vol.Required("session_id"): str,
    }
)
@websocket_api.async_response
async def handle_delete_session(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
):
    """Handle delete session command."""
    session_id = msg["session_id"]

    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict) and "manager" in data:
            await data["manager"].delete_session(session_id)

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "z2m_irrigation/sessions/clear",
    }
)
@websocket_api.async_response
async def handle_clear_sessions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
):
    """Handle clear all sessions command."""
    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict) and "manager" in data:
            await data["manager"].clear_sessions()

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "z2m_irrigation/schedules/list",
    }
)
@websocket_api.async_response
async def handle_list_schedules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
):
    """Handle list schedules command."""
    all_schedules = []
    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict) and "scheduler" in data:
            schedules = data["scheduler"].get_all_schedules()
            all_schedules.extend(schedules.values())

    connection.send_result(msg["id"], {"schedules": all_schedules})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "z2m_irrigation/schedules/get",
        vol.Required("schedule_id"): str,
    }
)
@websocket_api.async_response
async def handle_get_schedule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
):
    """Handle get schedule command."""
    schedule_id = msg["schedule_id"]

    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict) and "scheduler" in data:
            schedule = data["scheduler"].get_schedule(schedule_id)
            if schedule:
                connection.send_result(msg["id"], {"schedule": schedule})
                return

    connection.send_error(msg["id"], "not_found", "Schedule not found")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "z2m_irrigation/schedules/runs",
        vol.Optional("schedule_id"): str,
        vol.Optional("limit"): int,
    }
)
@websocket_api.async_response
async def handle_list_schedule_runs(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
):
    """Handle list schedule runs command."""
    schedule_id = msg.get("schedule_id")
    limit = msg.get("limit", 50)

    all_runs = []
    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict) and "scheduler" in data:
            scheduler = data["scheduler"]
            try:
                query = scheduler.history.supabase.table("schedule_runs").select("*")

                if schedule_id:
                    query = query.eq("schedule_id", schedule_id)

                result = await query.order("started_at", desc=True).limit(limit).execute()

                if result.data:
                    all_runs.extend(result.data)
            except Exception as e:
                _LOGGER.error("Failed to fetch schedule runs: %s", e)

    connection.send_result(msg["id"], {"runs": all_runs})
