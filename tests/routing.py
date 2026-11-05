"""Routing contracts use temporary records and local webhook receivers only."""
import json


def verify(api, anonymous):
    channels = []
    route = None
    configs = []
    try:
        for number in (1, 2):
            data = {'name': 'Routing contract receiver ' + str(number), 'kind': 'webhook',
                    'config': {'url': 'http://mock:8000/routing-contract-' + str(number)}, 'enabled': True}
            configs.append(data)
            channels.append(api.ok('/api/channels', data, 'POST')['id'])
        settings = {'name': 'Routing contract route', 'channel_ids': channels[:], 'enabled': True,
                    'min_priority': 1, 'required_tag': None}
        route = api.ok('/api/routes', settings, 'POST')
        key = {'X-Relay-Key': route['token']}
        def update(**changes):
            settings.update(changes)
            api.ok('/api/routes/' + route['id'], settings, 'PUT')
        def event(payload):
            return api.ok(route['endpoint'], payload, 'POST', key)
        def expect(result, queued, reason, matched=True, destinations=2, active=2):
            assert result['queued'] == queued, result
            routing = result['routing']
            assert routing['route_id'] == route['id'] and routing['route_name'] == settings['name']
            assert routing['matched'] == matched and routing['reason'] == reason, result
            assert routing['destinations'] == destinations and routing['active_destinations'] == active, result
            rows = api.ok('/api/deliveries?route_id=' + route['id'])['items']
            assert len([row for row in rows if row['event_id'] == result['event_id']]) == queued
            assert 'token' not in json.dumps(routing) and 'http://mock' not in json.dumps(routing)
            return routing
        # Priority and tags are independently optional, with priority 3 by default.
        basic = event({'title': 'No optional fields', 'message': 'Routing test'})
        assert expect(basic, 2, 'queued')['priority'] == 3
        for payload in ({'title': 'No tags', 'priority': 3}, {'tags': []}, {'priority': None, 'tags': None}):
            assert expect(event(payload), 2, 'queued')['priority'] == 3
        rows = api.ok('/api/deliveries?route_id=' + route['id'])['items']
        assert all(row['tags'] == [] for row in rows)
        update(min_priority=4)
        expect(event({'title': 'Default below minimum'}), 0, 'priority_below_minimum', matched=False)
        expect(event({'priority': 4}), 2, 'queued')
        update(min_priority=1, required_tag='prod')
        filtered = expect(event({'priority': 3}), 0, 'tag_mismatch', matched=False)
        assert not filtered['tags_match'] and filtered['required_tag'] == 'prod'
        expect(event({'tags': [' prod ']}), 2, 'queued')
        update(required_tag=None)
        api.ok('/api/channels/' + channels[1], {**configs[1], 'enabled': False}, 'PUT')
        mixed = expect(event({}), 1, 'queued', active=1)
        assert next(item for item in mixed['recipients'] if item['id'] == channels[1])['reason'] == 'destination_disabled'
        api.ok('/api/channels/' + channels[0], {**configs[0], 'enabled': False}, 'PUT')
        expect(event({}), 0, 'no_active_destinations', active=0)
        update(channel_ids=[])
        expect(event({}), 0, 'no_destinations', destinations=0, active=0)
        for number in (0, 1):
            api.ok('/api/channels/' + channels[number], configs[number], 'PUT')
        update(channel_ids=channels[:])
        test_path = '/api/routes/' + route['id'] + '/test'
        assert anonymous.request(test_path, {}, 'POST')[0] == 401
        tested = api.ok(test_path, {'title': 'Real UI test'}, 'POST')
        public = event({'title': 'Real public webhook'})
        assert tested['routing'] == public['routing']
        expect(tested, 2, 'queued')
        for payload in ({'tags': 'prod'}, {'tags': [3]}, {'priority': 'high'}, []):
            assert api.request(route['endpoint'], payload, 'POST', key)[0] == 400
        update(enabled=False)
        for path, headers in ((route['endpoint'], key), (test_path, {})):
            status, response = api.request(path, {}, 'POST', headers)
            assert status == 403 and response['routing']['reason'] == 'route_disabled'
            assert response['queued'] == 0
        status, response = anonymous.request(route['endpoint'], {}, 'POST', {'X-Relay-Key': 'invalid'})
        assert status == 401 and 'routing' not in response
        print('PASS: optional priority/tags, default priority 3, configured filters, disabled/missing recipients, routing reasons and authenticated real webhook tests', flush=True)
    finally:
        if route:
            api.ok('/api/routes/' + route['id'], method='DELETE')
        for channel in channels:
            api.ok('/api/channels/' + channel, method='DELETE')
