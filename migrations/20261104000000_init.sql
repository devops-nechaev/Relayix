CREATE TABLE channels (
 id UUID PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 config JSONB NOT NULL DEFAULT '{}'::jsonb,
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE routes (
 id UUID PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
 token_hash TEXT NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE,
 min_priority INT NOT NULL DEFAULT 1,
 required_tag TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE route_channels (
 route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
 channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 PRIMARY KEY(route_id,channel_id)
);
CREATE TABLE events (
 id UUID PRIMARY KEY, route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
 title TEXT NOT NULL, message TEXT NOT NULL, priority INT NOT NULL,
 tags JSONB NOT NULL DEFAULT '[]'::jsonb,
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE deliveries (
 id UUID PRIMARY KEY, event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'queued', attempts INT NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 locked_at TIMESTAMPTZ,
 error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 sent_at TIMESTAMPTZ
);
CREATE INDEX deliveries_ready ON deliveries(status,next_attempt_at);
CREATE INDEX deliveries_created ON deliveries(created_at DESC);
