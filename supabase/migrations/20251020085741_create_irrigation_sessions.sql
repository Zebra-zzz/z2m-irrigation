/*
  # Irrigation Session History

  Creates a table to track irrigation session history for water valves.

  1. New Tables
    - `irrigation_sessions`
      - `id` (uuid, primary key)
      - `valve_topic` (text, valve identifier)
      - `valve_name` (text, display name)
      - `started_at` (timestamptz, session start time)
      - `ended_at` (timestamptz, session end time)
      - `duration_minutes` (numeric, how long the valve was open)
      - `liters_used` (numeric, water consumed during session)
      - `flow_rate_avg` (numeric, average flow rate L/min)
      - `trigger_type` (text, manual/timed/volume/schedule)
      - `target_value` (numeric, target minutes or liters if applicable)
      - `created_at` (timestamptz, record creation time)

  2. Indexes
    - Index on valve_topic for fast filtering
    - Index on started_at for time-based queries

  3. Security
    - Enable RLS
    - Allow read access for authenticated users
    - Allow insert for authenticated users (for logging)
*/

-- Create the sessions table
CREATE TABLE IF NOT EXISTS irrigation_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  valve_topic text NOT NULL,
  valve_name text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  duration_minutes numeric DEFAULT 0,
  liters_used numeric DEFAULT 0,
  flow_rate_avg numeric DEFAULT 0,
  trigger_type text DEFAULT 'manual',
  target_value numeric,
  created_at timestamptz DEFAULT now()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_irrigation_sessions_valve ON irrigation_sessions(valve_topic);
CREATE INDEX IF NOT EXISTS idx_irrigation_sessions_started ON irrigation_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_sessions_trigger ON irrigation_sessions(trigger_type);

-- Enable Row Level Security
ALTER TABLE irrigation_sessions ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read session history (adjust if you need authentication)
CREATE POLICY "Allow read access to irrigation sessions"
  ON irrigation_sessions
  FOR SELECT
  USING (true);

-- Allow inserts for logging new sessions
CREATE POLICY "Allow insert irrigation sessions"
  ON irrigation_sessions
  FOR INSERT
  WITH CHECK (true);

-- Allow updates to close sessions
CREATE POLICY "Allow update irrigation sessions"
  ON irrigation_sessions
  FOR UPDATE
  USING (true)
  WITH CHECK (true);
