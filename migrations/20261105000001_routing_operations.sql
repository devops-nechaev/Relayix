ALTER TABLE events ADD COLUMN routing JSONB;
ALTER TABLE events ADD COLUMN idempotency_hash TEXT;
ALTER TABLE events ADD COLUMN payload_hash TEXT;
CREATE UNIQUE INDEX events_idempotency ON events(route_id,idempotency_hash) WHERE idempotency_hash IS NOT NULL;
CREATE INDEX events_history ON events(created_at DESC,id DESC);

CREATE TABLE route_fallback_channels (
 route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
 channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 PRIMARY KEY(route_id,channel_id)
);
CREATE TABLE event_fallback_channels (
 event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 PRIMARY KEY(event_id,channel_id)
);
ALTER TABLE deliveries ADD COLUMN is_fallback BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE deliveries ADD COLUMN cycle_attempts INT NOT NULL DEFAULT 0;
UPDATE deliveries SET cycle_attempts=attempts;
CREATE UNIQUE INDEX deliveries_event_channel ON deliveries(event_id,channel_id);
CREATE TABLE delivery_attempts (
 delivery_id UUID NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
 number INT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 finished_at TIMESTAMPTZ,
 status TEXT NOT NULL DEFAULT 'processing',
 error TEXT,
 PRIMARY KEY(delivery_id,number)
);
