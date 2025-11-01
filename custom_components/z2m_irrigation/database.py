from __future__ import annotations
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class IrrigationDatabase:
    """Local SQLite database for irrigation persistence"""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.db_path = Path(hass.config.config_dir) / "z2m_irrigation.db"
        self._conn: Optional[sqlite3.Connection] = None
        _LOGGER.info(f"💾 Irrigation database: {self.db_path}")

    async def async_init(self):
        """Initialize database connection and create tables"""
        await self.hass.async_add_executor_job(self._init_sync)

    def _init_sync(self):
        """Synchronous database initialization"""
        try:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
            _LOGGER.info("✅ Local irrigation database initialized")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to initialize database: {e}", exc_info=True)
            self._conn = None

    def _create_tables(self):
        """Create database tables if they don't exist"""
        if not self._conn:
            return

        cursor = self._conn.cursor()

        # Valve totals table (lifetime + resettable)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS valve_totals (
                valve_topic TEXT PRIMARY KEY,
                valve_name TEXT NOT NULL,
                lifetime_total_liters REAL DEFAULT 0,
                lifetime_total_minutes REAL DEFAULT 0,
                lifetime_session_count INTEGER DEFAULT 0,
                resettable_total_liters REAL DEFAULT 0,
                resettable_total_minutes REAL DEFAULT 0,
                resettable_session_count INTEGER DEFAULT 0,
                last_reset_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sessions table (complete history)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                valve_topic TEXT NOT NULL,
                valve_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_minutes REAL,
                volume_liters REAL DEFAULT 0,
                avg_flow_rate REAL,
                trigger_type TEXT DEFAULT 'manual',
                target_liters REAL,
                target_minutes REAL,
                completed_successfully INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_valve
            ON sessions(valve_topic)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_started
            ON sessions(started_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_ended
            ON sessions(ended_at DESC)
        """)

        self._conn.commit()
        _LOGGER.debug("✅ Database tables created/verified")

    async def load_valve_totals(self, valve_topic: str) -> Dict[str, float]:
        """Load persisted totals from local database"""
        return await self.hass.async_add_executor_job(
            self._load_valve_totals_sync, valve_topic
        )

    def _load_valve_totals_sync(self, valve_topic: str) -> Dict[str, float]:
        """Synchronous load of valve totals"""
        _LOGGER.debug(f"🔍 Loading valve totals for: {valve_topic}")

        default_totals = {
            "lifetime_total_liters": 0.0,
            "lifetime_total_minutes": 0.0,
            "lifetime_session_count": 0,
            "resettable_total_liters": 0.0,
            "resettable_total_minutes": 0.0,
            "resettable_session_count": 0,
        }

        if not self._conn:
            _LOGGER.warning(f"⚠️ Database not initialized - returning zeros")
            return default_totals

        try:
            # Ensure valve_topic is a string
            valve_topic_str = str(valve_topic) if valve_topic else ""
            if not valve_topic_str:
                _LOGGER.warning(f"⚠️ Empty valve_topic provided")
                return default_totals

            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM valve_totals WHERE valve_topic = ?",
                (valve_topic_str,)
            )
            row = cursor.fetchone()

            if row:
                totals = {
                    "lifetime_total_liters": float(row["lifetime_total_liters"]),
                    "lifetime_total_minutes": float(row["lifetime_total_minutes"]),
                    "lifetime_session_count": int(row["lifetime_session_count"]),
                    "resettable_total_liters": float(row["resettable_total_liters"]),
                    "resettable_total_minutes": float(row["resettable_total_minutes"]),
                    "resettable_session_count": int(row["resettable_session_count"]),
                }
                _LOGGER.info(f"✅ Loaded totals for {valve_topic}:")
                _LOGGER.info(f"   Lifetime: {totals['lifetime_total_liters']:.2f} L, {totals['lifetime_total_minutes']:.2f} min")
                _LOGGER.info(f"   Resettable: {totals['resettable_total_liters']:.2f} L, {totals['resettable_total_minutes']:.2f} min")
                return totals

            _LOGGER.info(f"ℹ️ No existing totals found for {valve_topic} - starting fresh")
            return default_totals

        except Exception as e:
            _LOGGER.error(f"❌ Error loading valve totals for '{valve_topic}': {e}", exc_info=True)
            _LOGGER.error(f"   valve_topic type: {type(valve_topic)}, value: {repr(valve_topic)}")
            return default_totals

    async def save_valve_totals(self, valve_topic: str, valve_name: str,
                                liters: float, minutes: float) -> Optional[Dict[str, float]]:
        """Update valve totals in database"""
        return await self.hass.async_add_executor_job(
            self._save_valve_totals_sync, valve_topic, valve_name, liters, minutes
        )

    def _save_valve_totals_sync(self, valve_topic: str, valve_name: str,
                                 liters: float, minutes: float) -> Optional[Dict[str, float]]:
        """Synchronous save of valve totals"""
        if not self._conn:
            return None

        try:
            cursor = self._conn.cursor()

            # Check if record exists
            cursor.execute(
                "SELECT * FROM valve_totals WHERE valve_topic = ?",
                (valve_topic,)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing record
                new_totals = {
                    "lifetime_total_liters": float(existing["lifetime_total_liters"]) + liters,
                    "lifetime_total_minutes": float(existing["lifetime_total_minutes"]) + minutes,
                    "lifetime_session_count": int(existing["lifetime_session_count"]) + 1,
                    "resettable_total_liters": float(existing["resettable_total_liters"]) + liters,
                    "resettable_total_minutes": float(existing["resettable_total_minutes"]) + minutes,
                    "resettable_session_count": int(existing["resettable_session_count"]) + 1,
                }

                cursor.execute("""
                    UPDATE valve_totals
                    SET valve_name = ?,
                        lifetime_total_liters = ?,
                        lifetime_total_minutes = ?,
                        lifetime_session_count = ?,
                        resettable_total_liters = ?,
                        resettable_total_minutes = ?,
                        resettable_session_count = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE valve_topic = ?
                """, (
                    valve_name,
                    new_totals["lifetime_total_liters"],
                    new_totals["lifetime_total_minutes"],
                    new_totals["lifetime_session_count"],
                    new_totals["resettable_total_liters"],
                    new_totals["resettable_total_minutes"],
                    new_totals["resettable_session_count"],
                    valve_topic
                ))
            else:
                # Insert new record
                new_totals = {
                    "lifetime_total_liters": liters,
                    "lifetime_total_minutes": minutes,
                    "lifetime_session_count": 1,
                    "resettable_total_liters": liters,
                    "resettable_total_minutes": minutes,
                    "resettable_session_count": 1,
                }

                cursor.execute("""
                    INSERT INTO valve_totals
                    (valve_topic, valve_name, lifetime_total_liters, lifetime_total_minutes,
                     lifetime_session_count, resettable_total_liters, resettable_total_minutes,
                     resettable_session_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    valve_topic, valve_name,
                    new_totals["lifetime_total_liters"],
                    new_totals["lifetime_total_minutes"],
                    new_totals["lifetime_session_count"],
                    new_totals["resettable_total_liters"],
                    new_totals["resettable_total_minutes"],
                    new_totals["resettable_session_count"]
                ))

            self._conn.commit()
            _LOGGER.debug(f"💾 Saved totals for {valve_topic}: +{liters:.2f}L, +{minutes:.2f}min")
            return new_totals

        except Exception as e:
            _LOGGER.error(f"❌ Error saving valve totals: {e}", exc_info=True)
            return None

    async def reset_resettable_totals(self, valve_topic: str) -> bool:
        """Reset only resettable totals (preserve lifetime)"""
        return await self.hass.async_add_executor_job(
            self._reset_resettable_totals_sync, valve_topic
        )

    def _reset_resettable_totals_sync(self, valve_topic: str) -> bool:
        """Synchronous reset of resettable totals"""
        if not self._conn:
            return False

        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE valve_totals
                SET resettable_total_liters = 0,
                    resettable_total_minutes = 0,
                    resettable_session_count = 0,
                    last_reset_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE valve_topic = ?
            """, (valve_topic,))

            self._conn.commit()
            _LOGGER.info(f"🔄 Reset resettable totals for {valve_topic} (lifetime preserved)")
            return True

        except Exception as e:
            _LOGGER.error(f"❌ Error resetting totals: {e}", exc_info=True)
            return False

    async def start_session(self, session_id: str, valve_topic: str, valve_name: str,
                           trigger_type: str = "manual", target_liters: Optional[float] = None,
                           target_minutes: Optional[float] = None) -> bool:
        """Log session start"""
        return await self.hass.async_add_executor_job(
            self._start_session_sync, session_id, valve_topic, valve_name,
            trigger_type, target_liters, target_minutes
        )

    def _start_session_sync(self, session_id: str, valve_topic: str, valve_name: str,
                            trigger_type: str, target_liters: Optional[float],
                            target_minutes: Optional[float]) -> bool:
        """Synchronous session start"""
        if not self._conn:
            return False

        try:
            cursor = self._conn.cursor()
            started_at = datetime.utcnow().isoformat()

            cursor.execute("""
                INSERT INTO sessions
                (session_id, valve_topic, valve_name, started_at, trigger_type,
                 target_liters, target_minutes, completed_successfully)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (session_id, valve_topic, valve_name, started_at, trigger_type,
                  target_liters, target_minutes))

            self._conn.commit()
            _LOGGER.info(f"🚿 Session started: {session_id} for {valve_name}")
            return True

        except Exception as e:
            _LOGGER.error(f"❌ Error starting session: {e}", exc_info=True)
            return False

    async def end_session(self, session_id: str, duration_minutes: float,
                         volume_liters: float, avg_flow_rate: float) -> bool:
        """Log session end and update totals"""
        return await self.hass.async_add_executor_job(
            self._end_session_sync, session_id, duration_minutes, volume_liters, avg_flow_rate
        )

    def _end_session_sync(self, session_id: str, duration_minutes: float,
                          volume_liters: float, avg_flow_rate: float) -> bool:
        """Synchronous session end"""
        if not self._conn:
            return False

        try:
            cursor = self._conn.cursor()
            ended_at = datetime.utcnow().isoformat()

            cursor.execute("""
                UPDATE sessions
                SET ended_at = ?,
                    duration_minutes = ?,
                    volume_liters = ?,
                    avg_flow_rate = ?,
                    completed_successfully = 1
                WHERE session_id = ?
            """, (ended_at, duration_minutes, volume_liters, avg_flow_rate, session_id))

            self._conn.commit()
            _LOGGER.info(f"🛑 Session ended: {session_id} - {duration_minutes:.2f}min, {volume_liters:.2f}L")
            return True

        except Exception as e:
            _LOGGER.error(f"❌ Error ending session: {e}", exc_info=True)
            return False

    async def get_usage_last_24h(self, valve_topic: str) -> Tuple[float, float]:
        """Get liters and minutes used in last 24 hours"""
        return await self.hass.async_add_executor_job(
            self._get_usage_last_24h_sync, valve_topic
        )

    def _get_usage_last_24h_sync(self, valve_topic: str) -> Tuple[float, float]:
        """Synchronous get 24h usage"""
        if not self._conn:
            return (0.0, 0.0)

        try:
            cursor = self._conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

            cursor.execute("""
                SELECT
                    COALESCE(SUM(volume_liters), 0) as total_liters,
                    COALESCE(SUM(duration_minutes), 0) as total_minutes
                FROM sessions
                WHERE valve_topic = ?
                  AND started_at >= ?
                  AND ended_at IS NOT NULL
            """, (valve_topic, cutoff))

            row = cursor.fetchone()
            return (float(row["total_liters"]), float(row["total_minutes"]))

        except Exception as e:
            _LOGGER.error(f"❌ Error getting 24h usage: {e}", exc_info=True)
            return (0.0, 0.0)

    async def get_usage_last_7d(self, valve_topic: str) -> Tuple[float, float]:
        """Get liters and minutes used in last 7 days"""
        return await self.hass.async_add_executor_job(
            self._get_usage_last_7d_sync, valve_topic
        )

    def _get_usage_last_7d_sync(self, valve_topic: str) -> Tuple[float, float]:
        """Synchronous get 7d usage"""
        if not self._conn:
            return (0.0, 0.0)

        try:
            cursor = self._conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

            cursor.execute("""
                SELECT
                    COALESCE(SUM(volume_liters), 0) as total_liters,
                    COALESCE(SUM(duration_minutes), 0) as total_minutes
                FROM sessions
                WHERE valve_topic = ?
                  AND started_at >= ?
                  AND ended_at IS NOT NULL
            """, (valve_topic, cutoff))

            row = cursor.fetchone()
            return (float(row["total_liters"]), float(row["total_minutes"]))

        except Exception as e:
            _LOGGER.error(f"❌ Error getting 7d usage: {e}", exc_info=True)
            return (0.0, 0.0)

    async def cleanup_old_sessions(self, days: int = 90):
        """Clean up sessions older than specified days"""
        return await self.hass.async_add_executor_job(
            self._cleanup_old_sessions_sync, days
        )

    def _cleanup_old_sessions_sync(self, days: int):
        """Synchronous cleanup of old sessions"""
        if not self._conn:
            return

        try:
            cursor = self._conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

            cursor.execute("""
                DELETE FROM sessions
                WHERE started_at < ?
            """, (cutoff,))

            deleted = cursor.rowcount
            self._conn.commit()

            if deleted > 0:
                _LOGGER.info(f"🧹 Cleaned up {deleted} old sessions (>{days} days)")

        except Exception as e:
            _LOGGER.error(f"❌ Error cleaning up sessions: {e}", exc_info=True)

    async def close(self):
        """Close database connection"""
        if self._conn:
            await self.hass.async_add_executor_job(self._conn.close)
            _LOGGER.info("💾 Database connection closed")
