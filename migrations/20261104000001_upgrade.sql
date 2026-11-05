-- Normalize empty optional route filters from v0.1.0. This migration preserves existing keys and routes.
UPDATE routes SET required_tag=NULL WHERE required_tag IS NOT NULL AND BTRIM(required_tag)='';
CREATE TABLE IF NOT EXISTS templates (
 id UUID PRIMARY KEY,
 name TEXT NOT NULL,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE routes ADD COLUMN IF NOT EXISTS template_id UUID REFERENCES templates(id) ON DELETE SET NULL;
