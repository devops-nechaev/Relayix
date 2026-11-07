"""Global ordering and durable table preferences, not page-local sorting."""
from urllib.parse import urlencode
import copy


def verify(api,anonymous):
    channels=[]
    route=None
    original=api.ok('/api/auth/me')['preferences']
    try:
        channel=api.ok('/api/channels',{'name':'Table receiver','kind':'webhook','config':{'url':'http://mock:8000/table-contract'}},'POST')['id']
        channels.append(channel)
        route=api.ok('/api/routes',{'name':'Table sorting','channel_ids':channels},'POST')
        titles=['Zulu '+str(n).zfill(2) for n in range(12)]+['Alpha '+str(n).zfill(2) for n in range(12)]
        for title in titles:
            api.ok(route['endpoint'],{'title':title},'POST',{'X-Relay-Key':route['token']})
        for resource in ('events','deliveries'):
            path='/api/'+resource
            def get(**kwargs):
                return api.ok(path+'?'+urlencode({'route_id':route['id'],'page_size':5,**kwargs}))
            first=get(sort_by='title',sort_dir='asc',page=1)
            second=get(sort_by='title',sort_dir='asc',page=2)
            assert [r['title'] for r in first['items']]==sorted(titles)[:5]
            assert [r['title'] for r in second['items']]==sorted(titles)[5:10]
            descending=get(sort_by='title',sort_dir='desc')
            assert [r['title'] for r in descending['items']]==sorted(titles,reverse=True)[:5]
            default=get()
            explicit=get(sort_by='created_at',sort_dir='desc')
            assert [r['id'] for r in default['items']]==[r['id'] for r in explicit['items']]
            latest=[r['created_at'] for r in default['items']]
            assert latest==sorted(latest,reverse=True)
            oldest=get(sort_by='created_at',sort_dir='asc')
            assert [r['created_at'] for r in oldest['items']]==sorted(r['created_at'] for r in oldest['items'])
            for bad in ({'sort_by':'title; DROP TABLE events'},{'sort_by':'details'},{'sort_dir':'sideways'}):
                assert api.request(path+'?'+urlencode(bad))[0]==400
        # Alert history sorting is also performed before its server result limit.
        for key in ('created_at','rule','recipient','status'):
            assert api.request('/api/alert-deliveries?'+urlencode({'sort_by':key,'sort_dir':'asc'}))[0]==200
        assert api.request('/api/alert-deliveries?sort_by=invalid')[0]==400
        prefs=copy.deepcopy(original)
        prefs['tables']={name:{'hidden_columns':['details'],'sort_by':'created_at','sort_dir':'desc'} for name in ('deliveries','dashboard_deliveries','incoming','alert_history')}
        prefs['tables']['users']={'hidden_columns':['role'],'sort_by':'user','sort_dir':'asc'}
        api.ok('/api/auth/preferences',prefs,'PUT')
        assert api.ok('/api/auth/me')['preferences']['tables']==prefs['tables']
        assert anonymous.request('/api/auth/preferences',prefs,'PUT')[0]==401
        for table_settings in ({'unknown':{'hidden_columns':[],'sort_by':'created_at','sort_dir':'desc'}},{'deliveries':{'hidden_columns':['nonexistent'],'sort_by':'created_at','sort_dir':'desc'}},{'incoming':{'hidden_columns':['created_at','title','route','routing','deliveries','details'],'sort_by':'created_at','sort_dir':'desc'}},{'users':{'hidden_columns':[],'sort_by':'actions','sort_dir':'asc'}}):
            assert api.request('/api/auth/preferences',{**original,'tables':table_settings},'PUT')[0]==400
        ordered=copy.deepcopy(prefs)
        ordered['tables']['incoming']['column_order']=['title','created_at','details','route','routing','deliveries']
        api.ok('/api/auth/preferences',ordered,'PUT')
        assert api.ok('/api/auth/me')['preferences']['tables']['incoming']['column_order']==ordered['tables']['incoming']['column_order']
        for invalid in (['title','title'],['unknown']):
            invalid_prefs=copy.deepcopy(ordered)
            invalid_prefs['tables']['incoming']['column_order']=invalid
            assert api.request('/api/auth/preferences',invalid_prefs,'PUT')[0]==400
        print('PASS: global text/time sorting across pages, newest-first defaults, SQL sort allowlists, all-table account preferences and visibility validation',flush=True)
    finally:
        api.ok('/api/auth/preferences',original,'PUT')
        if route:api.ok('/api/routes/'+route['id'],method='DELETE')
        for cid in channels:api.ok('/api/channels/'+cid,method='DELETE')
