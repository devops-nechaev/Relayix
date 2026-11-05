-- Keep applied migration files immutable; change defaults in a new migration.
ALTER TABLE alert_policies ALTER COLUMN title SET DEFAULT 'Relayix: delivery failures';
UPDATE alert_policies SET title = 'Relayix: delivery failures'
WHERE title = 'RelayNest: delivery failures';
