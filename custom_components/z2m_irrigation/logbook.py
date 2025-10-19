"""Logbook integration for Z2M Irrigation."""
from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import callback

from .const import DOMAIN, EVENT_SESSION_STARTED, EVENT_SESSION_ENDED


@callback
def async_describe_events(hass, async_describe_event):
    """Describe logbook events."""

    @callback
    def describe_session_started(event):
        """Describe session started event."""
        data = event.data
        valve = data.get("valve", "Unknown")
        mode = data.get("mode", "manual")

        if mode == "timed":
            target = f"{data.get('target_minutes')} minutes"
        elif mode == "litres":
            target = f"{data.get('target_litres')} L"
        else:
            target = "manual"

        return {
            LOGBOOK_ENTRY_NAME: "Irrigation Session",
            LOGBOOK_ENTRY_MESSAGE: f"started for {valve} ({target})",
        }

    @callback
    def describe_session_ended(event):
        """Describe session ended event."""
        data = event.data
        valve = data.get("valve", "Unknown")
        litres = data.get("litres", 0)
        duration = data.get("duration_min", 0)
        ended_by = data.get("ended_by", "unknown")

        return {
            LOGBOOK_ENTRY_NAME: "Irrigation Session",
            LOGBOOK_ENTRY_MESSAGE: f"ended for {valve}: {litres:.1f}L in {duration:.1f}min ({ended_by})",
        }

    async_describe_event(DOMAIN, EVENT_SESSION_STARTED, describe_session_started)
    async_describe_event(DOMAIN, EVENT_SESSION_ENDED, describe_session_ended)
