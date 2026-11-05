CREATE TABLE users (
 id UUID PRIMARY KEY,
 username TEXT NOT NULL UNIQUE,
 display_name TEXT NOT NULL,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK (role IN ('admin','member')),
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY,
 user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE login_attempts (
 username TEXT PRIMARY KEY,
 failures INT NOT NULL DEFAULT 0,
 window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE deliveries ADD COLUMN last_error_at TIMESTAMPTZ;
UPDATE deliveries SET last_error_at=COALESCE(locked_at,created_at) WHERE error IS NOT NULL;
CREATE INDEX deliveries_failure_time ON deliveries(last_error_at) WHERE error IS NOT NULL;
CREATE INDEX deliveries_channel_time ON deliveries(channel_id,created_at DESC);
CREATE INDEX events_route_time ON events(route_id,created_at DESC);

CREATE TABLE alert_policies (
 id UUID PRIMARY KEY,
 name TEXT NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 watch_channel_ids UUID[] NOT NULL DEFAULT '{}',
 watch_route_ids UUID[] NOT NULL DEFAULT '{}',
 destination_ids UUID[] NOT NULL,
 failure_threshold INT NOT NULL DEFAULT 1 CHECK(failure_threshold BETWEEN 1 AND 100),
 min_attempts INT NOT NULL DEFAULT 1 CHECK(min_attempts BETWEEN 1 AND 5),
 window_minutes INT NOT NULL DEFAULT 15 CHECK(window_minutes BETWEEN 1 AND 1440),
 cooldown_minutes INT NOT NULL DEFAULT 15 CHECK(cooldown_minutes BETWEEN 1 AND 1440),
 title TEXT NOT NULL DEFAULT 'RelayNest: delivery failures',
 body TEXT NOT NULL DEFAULT '{failures} delivery failure(s). Channel: {channel}. Route: {route}. Error: {error}',
 last_triggered_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE alert_incidents (
 policy_id UUID NOT NULL REFERENCES alert_policies(id) ON DELETE CASCADE,
 delivery_id UUID NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(policy_id,delivery_id)
);
-- Separate outbox: failure alerts never trigger more failure alerts.
CREATE TABLE alert_deliveries (
 id UUID PRIMARY KEY,
 policy_id UUID REFERENCES alert_policies(id) ON DELETE SET NULL,
 source_delivery_id UUID REFERENCES deliveries(id) ON DELETE SET NULL,
 channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 message TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued',
 attempts INT NOT NULL DEFAULT 0,
 error TEXT,
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 locked_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 sent_at TIMESTAMPTZ
);
CREATE INDEX alert_deliveries_ready ON alert_deliveries(status,next_attempt_at);
