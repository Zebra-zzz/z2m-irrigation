/*
  Irrigation Totals & History Persistence
  
  Purpose: Provides full persistence for irrigation data that survives Home Assistant restarts
  
  New Tables:
  1. irrigation_valve_totals - Lifetime totals that never reset
  2. irrigation_sessions - Complete session history (already referenced in schedules)
  3. irrigation_daily_stats - Daily aggregated statistics
  
  Security: Enable RLS with public read/write access for Home Assistant integration
*/

-- Table 1: Valve Totals (Lifetime + Resettable)
CREATE TABLE IF NOT EXISTS irrigation_valve_totals (
  valve_topic text PRIMARY KEY,
  valve_name text NOT NULL,
  
  -- Lifetime totals (NEVER reset)
  lifetime_total_liters numeric(12,2) DEFAULT 0 NOT NULL,
  lifetime_total_minutes numeric(12,2) DEFAULT 0 NOT NULL,
  lifetime_session_count integer DEFAULT 0 NOT NULL,
  
  -- Resettable totals (can be reset manually)
  resettable_total_liters numeric(12,2) DEFAULT 0 NOT NULL,
  resettable_total_minutes numeric(12,2) DEFAULT 0 NOT NULL,
  resettable_session_count integer DEFAULT 0 NOT NULL,
  
  -- Metadata
  last_reset_at timestamptz,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL
);

-- Table 2: Session History (complete log of every irrigation event)
CREATE TABLE IF NOT EXISTS irrigation_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  valve_topic text NOT NULL,
  valve_name text NOT NULL,
  
  -- Session timing
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  duration_minutes numeric(10,2),
  
  -- Water usage
  volume_liters numeric(10,2) DEFAULT 0,
  avg_flow_rate numeric(8,2),
  
  -- Session details
  trigger_type text DEFAULT 'manual' NOT NULL,
  target_liters numeric(10,2),
  target_minutes numeric(10,2),
  completed_successfully boolean DEFAULT true,
  
  -- Optional
  notes text,
  
  created_at timestamptz DEFAULT now() NOT NULL
);

-- Table 3: Daily Statistics
CREATE TABLE IF NOT EXISTS irrigation_daily_stats (
  date date NOT NULL,
  valve_topic text NOT NULL,
  
  total_liters numeric(10,2) DEFAULT 0 NOT NULL,
  total_minutes numeric(10,2) DEFAULT 0 NOT NULL,
  session_count integer DEFAULT 0 NOT NULL,
  avg_flow_rate numeric(8,2),
  
  PRIMARY KEY (date, valve_topic),
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_valve_topic ON irrigation_sessions(valve_topic);
CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON irrigation_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON irrigation_daily_stats(date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_stats_valve ON irrigation_daily_stats(valve_topic);

-- Enable Row Level Security
ALTER TABLE irrigation_valve_totals ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_daily_stats ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Public read/write for Home Assistant (no auth required for local instances)
CREATE POLICY "Public can read valve totals"
  ON irrigation_valve_totals FOR SELECT
  USING (true);

CREATE POLICY "Public can insert valve totals"
  ON irrigation_valve_totals FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Public can update valve totals"
  ON irrigation_valve_totals FOR UPDATE
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Public can read sessions"
  ON irrigation_sessions FOR SELECT
  USING (true);

CREATE POLICY "Public can insert sessions"
  ON irrigation_sessions FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Public can update sessions"
  ON irrigation_sessions FOR UPDATE
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Public can read daily stats"
  ON irrigation_daily_stats FOR SELECT
  USING (true);

CREATE POLICY "Public can insert daily stats"
  ON irrigation_daily_stats FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Public can update daily stats"
  ON irrigation_daily_stats FOR UPDATE
  USING (true)
  WITH CHECK (true);

-- Function to update updated_at timestamp (if doesn't exist)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_valve_totals_updated_at ON irrigation_valve_totals;
CREATE TRIGGER update_valve_totals_updated_at
  BEFORE UPDATE ON irrigation_valve_totals
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_daily_stats_updated_at ON irrigation_daily_stats;
CREATE TRIGGER update_daily_stats_updated_at
  BEFORE UPDATE ON irrigation_daily_stats
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
