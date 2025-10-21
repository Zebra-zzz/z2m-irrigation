from __future__ import annotations
import logging
import os
from datetime import datetime, date
from typing import Optional, Dict, Any
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class SessionHistory:
    """Persistent session history using Supabase"""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")

        if not self.supabase_url or not self.supabase_key:
            _LOGGER.warning("Supabase not configured - history will not persist across restarts")
            self._persistence_enabled = False
        else:
            self._persistence_enabled = True
            _LOGGER.info("Session history initialized with Supabase persistence")

    async def _supabase_request(self, method: str, table: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a request to Supabase REST API"""
        if not self._persistence_enabled:
            return None

        import aiohttp

        url = f"{self.supabase_url}/rest/v1/{table}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, params=params) as resp:
                        if resp.status in (200, 201):
                            return await resp.json()
                elif method == "POST":
                    async with session.post(url, headers=headers, json=data) as resp:
                        if resp.status in (200, 201):
                            return await resp.json()
                elif method == "PATCH":
                    async with session.patch(url, headers=headers, json=data, params=params) as resp:
                        if resp.status in (200, 204):
                            return await resp.json() if resp.status == 200 else {}

                _LOGGER.error("Supabase request failed: %s %s - Status %s", method, table, resp.status)
                return None

        except Exception as e:
            _LOGGER.error("Supabase request error: %s", e)
            return None

    async def load_valve_totals(self, valve_topic: str) -> Dict[str, float]:
        """Load persisted totals from Supabase"""
        if not self._persistence_enabled:
            return {
                "lifetime_total_liters": 0,
                "lifetime_total_minutes": 0,
                "lifetime_session_count": 0,
                "resettable_total_liters": 0,
                "resettable_total_minutes": 0,
                "resettable_session_count": 0,
            }

        result = await self._supabase_request(
            "GET",
            "irrigation_valve_totals",
            params={"valve_topic": f"eq.{valve_topic}", "select": "*"}
        )

        if result and len(result) > 0:
            row = result[0]
            _LOGGER.debug("Loaded persisted totals for %s: %s L, %s min",
                         valve_topic, row.get("lifetime_total_liters", 0), row.get("lifetime_total_minutes", 0))
            return {
                "lifetime_total_liters": float(row.get("lifetime_total_liters", 0)),
                "lifetime_total_minutes": float(row.get("lifetime_total_minutes", 0)),
                "lifetime_session_count": int(row.get("lifetime_session_count", 0)),
                "resettable_total_liters": float(row.get("resettable_total_liters", 0)),
                "resettable_total_minutes": float(row.get("resettable_total_minutes", 0)),
                "resettable_session_count": int(row.get("resettable_session_count", 0)),
            }

        return {
            "lifetime_total_liters": 0,
            "lifetime_total_minutes": 0,
            "lifetime_session_count": 0,
            "resettable_total_liters": 0,
            "resettable_total_minutes": 0,
            "resettable_session_count": 0,
        }

    async def update_valve_totals(self, valve_topic: str, valve_name: str,
                                  liters: float, minutes: float) -> Optional[Dict[str, float]]:
        """Update valve totals in Supabase (both lifetime and resettable)
        Returns the new totals so they can be synced to valve object"""
        if not self._persistence_enabled:
            return None

        try:
            # First, try to get existing totals
            existing = await self._supabase_request(
                "GET",
                "irrigation_valve_totals",
                params={"valve_topic": f"eq.{valve_topic}", "select": "*"}
            )

            new_data = {}
            if existing and len(existing) > 0:
                # Update existing record
                current = existing[0]
                new_data = {
                    "valve_name": valve_name,
                    "lifetime_total_liters": float(current.get("lifetime_total_liters", 0)) + liters,
                    "lifetime_total_minutes": float(current.get("lifetime_total_minutes", 0)) + minutes,
                    "lifetime_session_count": int(current.get("lifetime_session_count", 0)) + 1,
                    "resettable_total_liters": float(current.get("resettable_total_liters", 0)) + liters,
                    "resettable_total_minutes": float(current.get("resettable_total_minutes", 0)) + minutes,
                    "resettable_session_count": int(current.get("resettable_session_count", 0)) + 1,
                }
                await self._supabase_request(
                    "PATCH",
                    "irrigation_valve_totals",
                    data=new_data,
                    params={"valve_topic": f"eq.{valve_topic}"}
                )
            else:
                # Create new record
                new_data = {
                    "valve_topic": valve_topic,
                    "valve_name": valve_name,
                    "lifetime_total_liters": liters,
                    "lifetime_total_minutes": minutes,
                    "lifetime_session_count": 1,
                    "resettable_total_liters": liters,
                    "resettable_total_minutes": minutes,
                    "resettable_session_count": 1,
                }
                await self._supabase_request("POST", "irrigation_valve_totals", data=new_data)

            _LOGGER.debug("Updated totals for %s: +%.2f L, +%.2f min", valve_topic, liters, minutes)

            # Return the new totals
            return {
                "lifetime_total_liters": new_data["lifetime_total_liters"],
                "lifetime_total_minutes": new_data["lifetime_total_minutes"],
                "lifetime_session_count": new_data["lifetime_session_count"],
                "resettable_total_liters": new_data["resettable_total_liters"],
                "resettable_total_minutes": new_data["resettable_total_minutes"],
                "resettable_session_count": new_data["resettable_session_count"],
            }

        except Exception as e:
            _LOGGER.error("Failed to update valve totals: %s", e)
            return None

    async def reset_resettable_totals(self, valve_topic: str) -> bool:
        """Reset only the resettable totals (lifetime totals remain unchanged)"""
        if not self._persistence_enabled:
            _LOGGER.warning("Cannot reset - Supabase not configured")
            return False

        try:
            reset_data = {
                "resettable_total_liters": 0,
                "resettable_total_minutes": 0,
                "resettable_session_count": 0,
                "last_reset_at": datetime.utcnow().isoformat(),
            }
            result = await self._supabase_request(
                "PATCH",
                "irrigation_valve_totals",
                data=reset_data,
                params={"valve_topic": f"eq.{valve_topic}"}
            )

            if result is not None:
                _LOGGER.info("Reset resettable totals for %s (lifetime totals preserved)", valve_topic)
                return True
            return False

        except Exception as e:
            _LOGGER.error("Failed to reset totals: %s", e)
            return False

    async def start_session(self, valve_topic: str, valve_name: str,
                           trigger_type: str = "manual",
                           target_liters: Optional[float] = None,
                           target_minutes: Optional[float] = None) -> Optional[str]:
        """Start a new irrigation session and log to Supabase"""
        started_at = datetime.utcnow()

        # Store in-memory for fast access
        session_data = {
            "valve_topic": valve_topic,
            "valve_name": valve_name,
            "started_at": started_at,
            "trigger_type": trigger_type,
            "target_liters": target_liters,
            "target_minutes": target_minutes,
            "session_id": None,
        }

        if self._persistence_enabled:
            try:
                # Create session in Supabase
                db_data = {
                    "valve_topic": valve_topic,
                    "valve_name": valve_name,
                    "started_at": started_at.isoformat(),
                    "trigger_type": trigger_type,
                    "target_liters": target_liters,
                    "target_minutes": target_minutes,
                    "completed_successfully": False,
                }
                result = await self._supabase_request("POST", "irrigation_sessions", data=db_data)

                if result and len(result) > 0:
                    session_id = result[0]["id"]
                    session_data["session_id"] = session_id
                    self._sessions[session_id] = session_data
                    _LOGGER.info("Started session %s for %s (%s)", session_id, valve_name, trigger_type)
                    return session_id

            except Exception as e:
                _LOGGER.error("Failed to start session in Supabase: %s", e)

        # Fallback to in-memory only
        session_id = f"{valve_topic}_{started_at.timestamp()}"
        session_data["session_id"] = session_id
        self._sessions[session_id] = session_data
        return session_id

    async def end_session(self, session_id: str, duration_minutes: float,
                         liters_used: float, flow_rate_avg: float,
                         completed_successfully: bool = True) -> Optional[Dict[str, float]]:
        """End session and update both Supabase and daily stats
        Returns updated totals for syncing to valve object"""
        if session_id not in self._sessions:
            _LOGGER.warning("Session %s not found in memory", session_id)
            return None

        session = self._sessions[session_id]
        ended_at = datetime.utcnow()
        updated_totals = None

        try:
            if self._persistence_enabled:
                # Update session in Supabase
                update_data = {
                    "ended_at": ended_at.isoformat(),
                    "duration_minutes": duration_minutes,
                    "volume_liters": liters_used,
                    "avg_flow_rate": flow_rate_avg,
                    "completed_successfully": completed_successfully,
                }
                await self._supabase_request(
                    "PATCH",
                    "irrigation_sessions",
                    data=update_data,
                    params={"id": f"eq.{session_id}"}
                )

                # Update valve totals and get new values
                updated_totals = await self.update_valve_totals(
                    session["valve_topic"],
                    session["valve_name"],
                    liters_used,
                    duration_minutes
                )

                # Update daily stats
                await self._update_daily_stats(
                    session["valve_topic"],
                    date.today(),
                    liters_used,
                    duration_minutes,
                    flow_rate_avg
                )

            _LOGGER.info(
                "Session ended: %s - %.2f min, %.2f L, %.2f L/min avg",
                session["valve_name"], duration_minutes, liters_used, flow_rate_avg
            )

            return updated_totals

        except Exception as e:
            _LOGGER.error("Failed to end session: %s", e)
            return None
        finally:
            # Clean up in-memory session
            if session_id in self._sessions:
                del self._sessions[session_id]

    async def _update_daily_stats(self, valve_topic: str, stat_date: date,
                                  liters: float, minutes: float, flow_rate: float) -> None:
        """Update daily statistics"""
        if not self._persistence_enabled:
            return

        try:
            date_str = stat_date.isoformat()

            # Check if stats exist for today
            existing = await self._supabase_request(
                "GET",
                "irrigation_daily_stats",
                params={
                    "date": f"eq.{date_str}",
                    "valve_topic": f"eq.{valve_topic}",
                    "select": "*"
                }
            )

            if existing and len(existing) > 0:
                # Update existing stats
                current = existing[0]
                new_count = int(current.get("session_count", 0)) + 1
                new_liters = float(current.get("total_liters", 0)) + liters
                new_minutes = float(current.get("total_minutes", 0)) + minutes

                # Calculate new average flow rate
                old_avg = float(current.get("avg_flow_rate", 0))
                old_count = int(current.get("session_count", 0))
                new_avg = ((old_avg * old_count) + flow_rate) / new_count if new_count > 0 else flow_rate

                update_data = {
                    "total_liters": new_liters,
                    "total_minutes": new_minutes,
                    "session_count": new_count,
                    "avg_flow_rate": new_avg,
                }
                await self._supabase_request(
                    "PATCH",
                    "irrigation_daily_stats",
                    data=update_data,
                    params={
                        "date": f"eq.{date_str}",
                        "valve_topic": f"eq.{valve_topic}"
                    }
                )
            else:
                # Create new daily stats
                new_data = {
                    "date": date_str,
                    "valve_topic": valve_topic,
                    "total_liters": liters,
                    "total_minutes": minutes,
                    "session_count": 1,
                    "avg_flow_rate": flow_rate,
                }
                await self._supabase_request("POST", "irrigation_daily_stats", data=new_data)

        except Exception as e:
            _LOGGER.error("Failed to update daily stats: %s", e)

    async def get_recent_sessions(self, valve_topic: Optional[str] = None, limit: int = 50) -> list:
        """Retrieve recent session history from Supabase"""
        if not self._persistence_enabled:
            return []

        try:
            params = {
                "select": "*",
                "order": "started_at.desc",
                "limit": str(limit)
            }
            if valve_topic:
                params["valve_topic"] = f"eq.{valve_topic}"

            result = await self._supabase_request("GET", "irrigation_sessions", params=params)
            return result if result else []

        except Exception as e:
            _LOGGER.error("Failed to fetch session history: %s", e)
            return []

    async def get_daily_stats(self, valve_topic: Optional[str] = None, days: int = 30) -> list:
        """Retrieve daily statistics"""
        if not self._persistence_enabled:
            return []

        try:
            params = {
                "select": "*",
                "order": "date.desc",
                "limit": str(days)
            }
            if valve_topic:
                params["valve_topic"] = f"eq.{valve_topic}"

            result = await self._supabase_request("GET", "irrigation_daily_stats", params=params)
            return result if result else []

        except Exception as e:
            _LOGGER.error("Failed to fetch daily stats: %s", e)
            return []
