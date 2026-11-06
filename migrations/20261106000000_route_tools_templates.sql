-- Keep the pre-0.4 template tables and assignments inactive and intact.
CREATE TABLE message_templates (
 id UUID PRIMARY KEY,
 name TEXT NOT NULL,
 title TEXT NOT NULL DEFAULT '',
 body TEXT NOT NULL,
 link_label TEXT NOT NULL DEFAULT 'Runner log',
 link_url TEXT NOT NULL DEFAULT '',
 link_failure_only BOOLEAN NOT NULL DEFAULT TRUE,
 version INTEGER NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE routes ADD COLUMN icon TEXT NOT NULL DEFAULT 'git-branch';
ALTER TABLE routes ADD COLUMN message_template_id UUID REFERENCES message_templates(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN rendered_payload JSONB;
ALTER TABLE events ADD COLUMN template_snapshot JSONB;
ALTER TABLE events ADD COLUMN template_result JSONB;
