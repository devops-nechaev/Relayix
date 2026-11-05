-- Historical fixtures for the isolated test database only. Never run against production.
BEGIN;
DELETE FROM routes WHERE id='00000000-0000-4000-8000-000000005001';
DELETE FROM channels WHERE id='00000000-0000-4000-8000-000000005000';
INSERT INTO channels(id,name,kind,config,enabled) VALUES('00000000-0000-4000-8000-000000005000','Monitoring history fixture','webhook','{"url":"http://mock:8000/period-fixture"}',false);
INSERT INTO routes(id,name,slug,token_hash,enabled) VALUES('00000000-0000-4000-8000-000000005001','Monitoring history fixture','monitoring-history-fixture',REPEAT('0',64),false);
WITH fixtures(n,age,status,error) AS (VALUES
 (1,INTERVAL '2 minutes','sent',NULL::text),
 (2,INTERVAL '10 minutes','sent',NULL::text),
 (3,INTERVAL '20 minutes','sent',NULL::text),
 (4,INTERVAL '45 minutes','sent',NULL::text),
 (5,INTERVAL '2 hours','sent',NULL::text),
 (6,INTERVAL '2 days','sent',NULL::text),
 (7,INTERVAL '10 days','sent',NULL::text),
 (8,INTERVAL '40 days','sent',NULL::text),
 (9,INTERVAL '3 minutes','failed','Historical fixture failure'),
 (10,INTERVAL '4 minutes','queued',NULL::text),
 (11,INTERVAL '4 minutes','queued','Historical fixture retry')
)
INSERT INTO events(id,route_id,title,message,priority,tags,payload,created_at)
SELECT MD5('relayix-monitoring-event-'||n)::uuid,'00000000-0000-4000-8000-000000005001','Monitoring fixture '||n,'Historical period check',3,'["period-fixture"]',JSONB_BUILD_OBJECT('fixture',true,'status',status,'error',error),NOW()-age FROM fixtures;
INSERT INTO deliveries(id,event_id,channel_id,status,attempts,next_attempt_at,error,created_at,sent_at,last_error_at)
SELECT MD5('relayix-monitoring-delivery-'||id::text)::uuid,id,'00000000-0000-4000-8000-000000005000',payload->>'status',CASE WHEN payload->>'status'='failed' THEN 5 WHEN payload->>'error' IS NOT NULL THEN 1 ELSE 0 END,NOW()+INTERVAL '1 day',payload->>'error',created_at,CASE WHEN payload->>'status'='sent' THEN created_at+INTERVAL '1 second' ELSE NULL END,CASE WHEN payload->>'error' IS NOT NULL THEN created_at ELSE NULL END
FROM events WHERE route_id='00000000-0000-4000-8000-000000005001';
COMMIT;
