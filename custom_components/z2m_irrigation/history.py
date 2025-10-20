from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)

_LOGGER = logging.getLogger(__name__)

class SessionHistory:
    """Local session history using Home Assistant's recorder database"""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._sessions = {}  # In-memory session tracking
        _LOGGER.debug("Session history initialized with HA recorder")

    async def start_session(self, valve_topic: str, valve_name: str, trigger_type: str = "manual", target_value: Optional[float] = None) -> Optional[str]:
        """Log the start of an irrigation session, returns session_id"""
        session_id = f"{valve_topic}_{datetime.now().timestamp()}"
        self._sessions[session_id] = {
            "valve_topic": valve_topic,
            "valve_name": valve_name,
            "started_at": datetime.now(),
            "trigger_type": trigger_type,
            "target_value": target_value,
        }
        _LOGGER.debug("Started session %s for %s (%s)", session_id, valve_name, trigger_type)
        return session_id

    async def end_session(self, session_id: str, duration_minutes: float, liters_used: float, flow_rate_avg: float):
        """Update session with end time and record to HA statistics"""
        if session_id not in self._sessions:
            return

        session = self._sessions[session_id]
        ended_at = datetime.now()

        # Log to HA statistics for long-term storage
        try:
            # Record session statistics
            statistic_id = f"z2m_irrigation:{session['valve_topic']}_sessions"
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{session['valve_name']} Sessions",
                source="z2m_irrigation",
                statistic_id=statistic_id,
                unit_of_measurement="L",
            )

            statistics = [
                StatisticData(
                    start=session["started_at"],
                    state=liters_used,
                    sum=liters_used,
                )
            ]

            async_add_external_statistics(self.hass, metadata, statistics)

            _LOGGER.info(
                "Session ended: %s - %.2f min, %.2f L, %.2f L/min avg",
                session["valve_name"], duration_minutes, liters_used, flow_rate_avg
            )

            # Clean up in-memory session
            del self._sessions[session_id]

        except Exception as e:
            _LOGGER.error("Failed to record session statistics: %s", e)

    async def get_recent_sessions(self, valve_topic: Optional[str] = None, limit: int = 50):
        """Retrieve recent session history from HA statistics"""
        try:
            statistic_id = f"z2m_irrigation:{valve_topic}_sessions" if valve_topic else None
            # Use HA's statistics API to retrieve historical data
            # This queries the local SQLite/PostgreSQL database
            return []  # Simplified for now - full implementation would query statistics_during_period
        except Exception as e:
            _LOGGER.error("Failed to fetch session history: %s", e)
            return []
