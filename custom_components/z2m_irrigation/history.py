from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

_LOGGER = logging.getLogger(__name__)

class SessionHistory:
    def __init__(self):
        self.client: Optional[Client] = None
        self._supabase_available = False
        self._init_client()

    def _init_client(self):
        try:
            # Try to import supabase library
            try:
                from supabase import create_client
                self._supabase_available = True
            except ImportError:
                _LOGGER.info("Supabase library not available, session history disabled")
                return

            url = os.getenv("VITE_SUPABASE_URL")
            key = os.getenv("VITE_SUPABASE_SUPABASE_ANON_KEY")
            if url and key:
                self.client = create_client(url, key)
                _LOGGER.debug("Supabase client initialized for session history")
            else:
                _LOGGER.info("Supabase credentials not found, session history disabled")
        except Exception as e:
            _LOGGER.warning("Failed to initialize Supabase client: %s", e)
            self.client = None

    async def start_session(self, valve_topic: str, valve_name: str, trigger_type: str = "manual", target_value: Optional[float] = None) -> Optional[str]:
        """Log the start of an irrigation session, returns session_id"""
        if not self.client:
            return None

        try:
            data = {
                "valve_topic": valve_topic,
                "valve_name": valve_name,
                "started_at": datetime.utcnow().isoformat(),
                "trigger_type": trigger_type,
                "target_value": target_value,
            }
            result = self.client.table("irrigation_sessions").insert(data).execute()
            if result.data and len(result.data) > 0:
                session_id = result.data[0].get("id")
                _LOGGER.debug("Started session %s for %s", session_id, valve_topic)
                return session_id
        except Exception as e:
            _LOGGER.error("Failed to log session start: %s", e)
        return None

    async def end_session(self, session_id: str, duration_minutes: float, liters_used: float, flow_rate_avg: float):
        """Update session with end time and totals"""
        if not self.client or not session_id:
            return

        try:
            data = {
                "ended_at": datetime.utcnow().isoformat(),
                "duration_minutes": round(duration_minutes, 2),
                "liters_used": round(liters_used, 2),
                "flow_rate_avg": round(flow_rate_avg, 3),
            }
            self.client.table("irrigation_sessions").update(data).eq("id", session_id).execute()
            _LOGGER.debug("Ended session %s: %.2f min, %.2f L", session_id, duration_minutes, liters_used)
        except Exception as e:
            _LOGGER.error("Failed to log session end: %s", e)

    async def get_recent_sessions(self, valve_topic: Optional[str] = None, limit: int = 50):
        """Retrieve recent session history"""
        if not self.client:
            return []

        try:
            query = self.client.table("irrigation_sessions").select("*").order("started_at", desc=True).limit(limit)
            if valve_topic:
                query = query.eq("valve_topic", valve_topic)
            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            _LOGGER.error("Failed to fetch session history: %s", e)
            return []
