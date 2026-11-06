"""Presentation contracts: original payloads, local Mattermost receivers only."""
import json
import time
from runtime import credentials
from urllib.request import urlopen


def verify(api, anonymous):
    channels=[]
    route=None
    definitions=[
        {'name':'Content webhook','kind':'mattermost','config':{'url':'http://mock:8000/message-content-contract'}},
        {'name':'Content channel','kind':'mattermost','config':{'mode':'bot','url':'http://mock:8000','bot_token':credentials['mattermost_token'],'target':'channel','channel_id':'formatcontract'}},
        {'name':'Content DM','kind':'mattermost','config':{'mode':'bot','url':'http://mock:8000','bot_token':credentials['mattermost_token'],'target':'direct','recipient':'@ops-bot'}},
    ]
    try:
        for definition in definitions:
            channels.append(api.ok('/api/channels',definition,'POST')['id'])
        route=api.ok('/api/routes',{'name':'Content contract','channel_ids':channels},'POST')
        cases=[
            ({'message':'Body 0 only'},'title_and_message','original','Body 0 only'),
            ({'title':'','message':'Body 1 empty title'},'title_and_message','original','Body 1 empty title'),
            ({'title':'  \t','message':'Body 2 blank title'},'title_and_message','original','Body 2 blank title'),
            ({'title':'Title 3','message':'Body 3'},'title_and_message','original','Title 3\n\nBody 3'),
            ({'title':'Title 4 only'},'title_and_message','original','Title 4 only'),
            ({'title':'Hidden title 5','message':'  Body 5\n\n'},'message_only','original','  Body 5\n\n'),
            ({'message':'**Passed 6** ✅\n<script>x</script> &'},'title_and_message','portable','**Passed 6** ✅\n&lt;script&gt;x&lt;/script&gt; &amp;'),
            ({'title':'[Title 7]','message':'**Passed 7**'},'title_and_message','portable',r'**\[Title 7\]**'+'\n\n**Passed 7**'),
            ({'title':'Hidden 8','message':'**Passed 8**'},'message_only','portable','**Passed 8**'),
            ({'title':'  ','message':'Body 9 **bold**'},'title_and_message','portable','Body 9 **bold**'),
            ({'message':'Tasks 10:\n[TASK-123](https://tickets.example.org/project/Task/TASK-123)'},'message_only','portable','Tasks 10:\n[TASK\\-123](https://tickets.example.org/project/Task/TASK-123)'),
        ]
        for index,(payload,mode,formatting,expected) in enumerate(cases):
            for cid,definition in zip(channels,definitions):
                config={**definition['config'],'message_mode':mode,'text_format':formatting}
                api.ok('/api/channels/'+cid,{**definition,'config':config},'PUT')
            result=api.ok(route['endpoint'],payload,'POST',{'X-Relay-Key':route['token']})
            assert result['queued']==3
            for _ in range(120):
                rows=api.ok('/api/deliveries?event_id='+result['event_id'])['items']
                if len(rows)==3 and all(r['status']=='sent' for r in rows):break
                time.sleep(.1)
            else:raise AssertionError(('Content delivery did not complete',index,rows))
            received=json.load(urlopen('http://mock:8000/received'))
            matching=[]
            for item in received:
                if item.get('path') not in ('/message-content-contract','/api/v4/posts'):continue
                body=json.loads(item['body'])
                if body.get('text',body.get('message'))==expected:matching.append(item)
            assert len(matching)==3,(index,expected,matching)
            event=next(e for e in api.ok('/api/events?route_id='+route['id'])['items'] if e['id']==result['event_id'])
            if 'message' in payload:assert event['message']==payload['message']
            has_title=bool(payload.get('title','').strip())
            assert event['has_title']==has_title and all(r['has_title']==has_title for r in rows)
            if not has_title:assert event['title']=='' and all(r['title']=='' for r in rows)
            assert all('payload' not in r for r in rows) and '_source' not in event
        saved=next(c for c in api.ok('/api/channels') if c['id']==channels[1])
        assert saved['config']['message_mode']=='message_only' and saved['config']['text_format']=='portable'
        api.ok('/api/channels/'+channels[1],saved,'PUT')
        for key,value in [('message_mode','invalid'),('text_format',True)]:
            assert api.request('/api/channels/'+channels[1],{**saved,'config':{**saved['config'],key:value}},'PUT')[0]==400
        print('PASS: absent/empty/blank titles, title-only and message-only delivery, original spacing, portable bold/escaping, unchanged history and masked edits across Mattermost webhook/channel/DM',flush=True)
    finally:
        if route:api.ok('/api/routes/'+route['id'],method='DELETE')
        for cid in channels:api.ok('/api/channels/'+cid,method='DELETE')
