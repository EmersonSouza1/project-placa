CREATE TABLE IF NOT EXISTS dock_events (
    event_id uuid PRIMARY KEY,
    visit_id uuid NOT NULL,
    camera_id varchar(80) NOT NULL,
    dock_id varchar(80) NOT NULL,
    stream_id uuid NOT NULL,
    track_id bigint NOT NULL CHECK (track_id >= 0),
    event_type text NOT NULL CHECK (event_type IN ('entered','observed_inside','exited','tracking_lost')),
    occurred_at timestamptz NOT NULL,
    plate varchar(7),
    plate_confidence double precision,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((plate IS NULL AND plate_confidence IS NULL) OR
           (plate IS NOT NULL AND plate_confidence IS NOT NULL AND plate_confidence BETWEEN 0 AND 1))
);
CREATE INDEX IF NOT EXISTS ix_events_dock_time ON dock_events(dock_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_visit ON dock_events(visit_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_visit_start ON dock_events(visit_id)
    WHERE event_type IN ('entered','observed_inside');
CREATE UNIQUE INDEX IF NOT EXISTS ux_visit_end ON dock_events(visit_id)
    WHERE event_type IN ('exited','tracking_lost');

CREATE TABLE IF NOT EXISTS dock_stays (
    visit_id uuid PRIMARY KEY,
    camera_id varchar(80) NOT NULL,
    dock_id varchar(80) NOT NULL,
    stream_id uuid NOT NULL,
    track_id bigint NOT NULL,
    started_at timestamptz,
    ended_at timestamptz,
    start_type text,
    end_type text,
    status text NOT NULL CHECK (status IN ('open','completed','interrupted','awaiting_start')),
    duration_seconds double precision,
    plate varchar(7),
    plate_confidence double precision,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at)
);
CREATE INDEX IF NOT EXISTS ix_stays_dock_time ON dock_stays(dock_id, started_at DESC);

