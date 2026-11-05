ALTER TABLE users ADD COLUMN preferences JSONB NOT NULL DEFAULT '{}'::jsonb;
-- The administrator API token is a separate identity from personal accounts.
CREATE TABLE api_preferences (
 id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(id),
 preferences JSONB NOT NULL DEFAULT '{}'::jsonb
);
INSERT INTO api_preferences(id) VALUES(TRUE);
CREATE INDEX events_tags_gin ON events USING GIN(tags);
