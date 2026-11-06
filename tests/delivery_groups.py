"""Event pagination and same-recipient filters against isolated PostgreSQL."""
import json
import subprocess
import uuid
from urllib.parse import urlencode

def verify(api,anonymous):
    channels=[]
    route=None
    original=api.ok('/api/auth/me')['preferences']
    def sql(statement):
        subprocess.run(['psql','--no-psqlrc','-v','ON_ERROR_STOP=1','-c',statement],check=True,capture_output=True)
    try:
        for name in ['DevOps','CI alerts','Fallback']:
            channels.append(api.ok('/api/channels',{'name':'Grouped '+name,'kind':'webhook','config':{'url':'http://mock:8000/grouped-contract'}},'POST')['id'])
        route=api.ok('/api/routes',{'name':'Grouped contract','channel_ids':channels[:2],'fallback_channel_ids':channels[2:]},'POST')
        event_ids=[]
        titles=['Alpha','Beta']+['Zulu '+str(i).zfill(2) for i in range(18)]
        for i,title in enumerate(titles):
            eid=str(uuid.uuid4());event_ids.append(eid)
            payload={'title':title,'message':'**Passed**\n[Task](https://example.org/task)','tags':['release'] if i==0 else []}
            sql("INSERT INTO events(id,route_id,title,message,priority,tags,payload,created_at) VALUES ('%s','%s','%s','%s',3,'%s','%s',NOW()-INTERVAL '%s minutes')"%(eid,route['id'],title,payload['message'],json.dumps(payload['tags']),json.dumps(payload),i))
            for index,cid in enumerate(channels):
                status='failed' if (i,index) in [(0,0),(1,1)] else 'queued' if index==2 and i in (0,2) else 'processing' if (i,index)==(1,2) else 'sent'
                error="'Receiver rejected'" if status=='failed' else "'Retry after outage'" if (i,index)==(0,2) else 'NULL'
                sql("INSERT INTO deliveries(id,event_id,channel_id,status,attempts,error,is_fallback,next_attempt_at,locked_at,created_at) VALUES ('%s','%s','%s','%s',%s,%s,%s,NOW()+INTERVAL '1 day',NOW(),NOW()-INTERVAL '%s minutes')"%(str(uuid.uuid4()),eid,cid,status,5 if status=='failed' else 1,error,'TRUE' if index==2 else 'FALSE',i))
        def get(**filters):return api.ok('/api/deliveries?'+urlencode({'group_events':'true','route_id':route['id'],**filters}))
        first=get(page_size=3,sort_by='title',sort_dir='asc')
        second=get(page_size=3,sort_by='title',sort_dir='asc',page=2)
        assert first['grouped'] and first['total']==20
        assert [e['title'] for e in first['items']]==sorted(titles)[:3]
        assert [e['title'] for e in second['items']]==sorted(titles)[3:6]
        assert set(e['id'] for e in first['items']).isdisjoint(e['id'] for e in second['items'])
        assert all(len(e['recipients'])==3 for e in first['items']+second['items'])
        alpha=get(channel_id=channels[0],status='failed')
        assert alpha['total']==1 and alpha['items'][0]['id']==event_ids[0]
        event=alpha['items'][0]
        assert len(event['recipients'])==3 and sum(r['matches_filter'] for r in event['recipients'])==1
        assert next(r for r in event['recipients'] if r['matches_filter'])['channel_id']==channels[0]
        beta=get(channel_id=channels[1],status='failed')
        assert beta['total']==1 and beta['items'][0]['id']==event_ids[1]
        assert get(status='failed')['total']==2
        assert get(channel_id=channels[0],status='retrying')['total']==0
        assert get(status='retrying')['total']==1
        assert get(status='queued')['total']==1
        assert get(status='processing')['total']==1
        assert get(search='Receiver rejected',channel_id=channels[0])['total']==1
        assert get(search='Receiver rejected',channel_id=channels[2])['total']==0
        assert get(tag='release')['total']==1
        assert get(event_id=event_ids[0])['total']==1
        assert get(period='5m')['total']==5
        assert get(page=99)['items']==[]
        for key in ('created_at','title','tags','route','recipients'):
            assert get(sort_by=key,sort_dir='desc')['total']==20
        for bad in ('status','attempts','details','title; DROP TABLE events'):
            assert api.request('/api/deliveries?'+urlencode({'group_events':'true','sort_by':bad}))[0]==400
        assert anonymous.request('/api/deliveries?group_events=true')[0]==401
        for hidden in [['title','title'],['created_at','title','tags','route','recipients','details'],['a','b','c','d','e','f']]:
            bad={**original,'tables':{'deliveries':{'sort_by':'created_at','sort_dir':'desc','hidden_columns':hidden}}}
            assert api.request('/api/auth/preferences',bad,'PUT')[0]==400
        assert api.ok('/api/deliveries?route_id='+route['id'])['total']==60
        assert 'payload' not in event and all(not {'message','payload','config','title'}.intersection(r) for r in event['recipients'])
        prefs={**original,'tables':{'deliveries':{'sort_by':'attempts','sort_dir':'asc','hidden_columns':['channel','status','attempts']}}}
        saved=api.ok('/api/auth/preferences',prefs,'PUT')['tables']['deliveries']
        assert saved=={'sort_by':'created_at','sort_dir':'desc','hidden_columns':['recipients']}
        assert api.ok('/api/auth/me')['preferences']['tables']['deliveries']==saved
        print('PASS: server-grouped complete-event pagination, same-recipient filters, context recipients, pending/fallback states, compact response, SQL sort allowlists and legacy preference migration',flush=True)
    finally:
        api.ok('/api/auth/preferences',original,'PUT')
        if route:api.ok('/api/routes/'+route['id'],method='DELETE')
        for cid in channels:api.ok('/api/channels/'+cid,method='DELETE')
