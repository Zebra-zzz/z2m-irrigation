/*
  # Irrigation Scheduling System

  1. New Tables
    - `irrigation_schedules`
      - `id` (uuid, primary key) - Unique schedule identifier
      - `name` (text) - User-friendly schedule name
      - `valve_topic` (text) - Which valve to control (e.g., "Water Valve 1")
      - `enabled` (boolean) - Whether schedule is active
      - `schedule_type` (text) - 'time_based' or 'interval'
      - `times` (jsonb) - Array of HH:MM times for time_based schedules
      - `days_of_week` (jsonb) - Array [0-6] for Mon-Sun (null = every day)
      - `interval_hours` (integer) - Hours between runs for interval type
      - `run_type` (text) - 'duration' or 'volume'
      - `run_value` (float) - Minutes or liters to run
      - `conditions` (jsonb) - Smart conditions (weather, sensors, etc.)
      - `priority` (integer) - Higher priority runs first if overlap (default 0)
      - `created_at`, `updated_at` - Timestamps
      - `last_run_at` (timestamptz) - When last executed
      - `next_run_at` (timestamptz) - When scheduled to run next
      - `created_by` (uuid) - User who created (references auth.users)

    - `schedule_runs`
      - `id` (uuid, primary key)
      - `schedule_id` (uuid) - References irrigation_schedules
      - `session_id` (uuid) - References irrigation_sessions
      - `started_at` (timestamptz) - When run started
      - `completed_at` (timestamptz) - When run finished
      - `status` (text) - 'running', 'completed', 'skipped', 'failed'
      - `skip_reason` (text) - Why skipped (rain, moisture, manual, etc.)
      - `actual_duration` (float) - Minutes actually run
      - `actual_volume` (float) - Liters actually used

  2. Security
    - Enable RLS on both tables
    - Authenticated users can manage their schedules
    - Schedule runs are read-only for users (created by system)

  3. Indexes
    - Index on valve_topic for fast lookups
    - Index on next_run_at for scheduler queries
    - Index on enabled for active schedule queries
*/

-- Create schedules table
CREATE TABLE IF NOT EXISTS irrigation_schedules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  valve_topic text NOT NULL,
  enabled boolean DEFAULT true,
  
  -- Scheduling configuration
  schedule_type text NOT NULL CHECK (schedule_type IN ('time_based', 'interval')),
  times jsonb DEFAULT '[]'::jsonb,
  days_of_week jsonb DEFAULT NULL,
  interval_hours integer DEFAULT NULL,
  
  -- Run configuration
  run_type text NOT NULL CHECK (run_type IN ('duration', 'volume')),
  run_value float NOT NULL CHECK (run_value > 0),
  
  -- Advanced features
  conditions jsonb DEFAULT '{}'::jsonb,
  priority integer DEFAULT 0,
  
  -- Metadata
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  last_run_at timestamptz DEFAULT NULL,
  next_run_at timestamptz DEFAULT NULL,
  created_by uuid DEFAULT auth.uid(),
  
  -- Constraints
  CONSTRAINT valid_time_based CHECK (
    schedule_type != 'time_based' OR (times IS NOT NULL AND jsonb_array_length(times) > 0)
  ),
  CONSTRAINT valid_interval CHECK (
    schedule_type != 'interval' OR (interval_hours IS NOT NULL AND interval_hours > 0)
  )
);

-- Create schedule runs history table
CREATE TABLE IF NOT EXISTS schedule_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  schedule_id uuid REFERENCES irrigation_schedules(id) ON DELETE CASCADE,
  session_id uuid REFERENCES irrigation_sessions(id) ON DELETE SET NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz DEFAULT NULL,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'skipped', 'failed', 'cancelled')),
  skip_reason text DEFAULT NULL,
  actual_duration float DEFAULT NULL,
  actual_volume float DEFAULT NULL
);

-- Enable RLS
ALTER TABLE irrigation_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedule_runs ENABLE ROW LEVEL SECURITY;

-- RLS Policies for schedules
CREATE POLICY "Authenticated users can view all schedules"
  ON irrigation_schedules FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Authenticated users can create schedules"
  ON irrigation_schedules FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = created_by);

CREATE POLICY "Users can update their own schedules"
  ON irrigation_schedules FOR UPDATE
  TO authenticated
  USING (auth.uid() = created_by)
  WITH CHECK (auth.uid() = created_by);

CREATE POLICY "Users can delete their own schedules"
  ON irrigation_schedules FOR DELETE
  TO authenticated
  USING (auth.uid() = created_by);

-- RLS Policies for schedule runs
CREATE POLICY "Authenticated users can view all schedule runs"
  ON schedule_runs FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "System can create schedule runs"
  ON schedule_runs FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "System can update schedule runs"
  ON schedule_runs FOR UPDATE
  TO authenticated
  USING (true);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_schedules_valve_topic ON irrigation_schedules(valve_topic);
CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON irrigation_schedules(next_run_at) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON irrigation_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule_id ON schedule_runs(schedule_id);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_status ON schedule_runs(status);

-- Function to automatically update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for updated_at
DROP TRIGGER IF EXISTS update_schedules_updated_at ON irrigation_schedules;
CREATE TRIGGER update_schedules_updated_at
  BEFORE UPDATE ON irrigation_schedules
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();