"""MTProto/WEB wiring and error redaction checks; no Telegram connections."""
import asyncio
import sys,secrets,uuid
sys.path.insert(0,"/app/transport")
import importlib.util
from pathlib import Path
from telethon import connection, types
from telethon_webproxy import ConnectionWebProxy

spec=importlib.util.spec_from_file_location('relayix_telegram',Path('/app/transport/telegram_send.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
cfg={'proxy_type':'mtproto','proxy_host':'proxy.example.org','proxy_port':'443','proxy_secret':'dd'+secrets.token_hex(16),
     'api_id':'12345','api_hash':secrets.token_hex(16),'bot_token':secrets.token_urlsafe(32),'chat_id':'@fixture','message_thread_id':'42'}
assert module.options(cfg)['connection'] is connection.ConnectionTcpMTProxyRandomizedIntermediate
for prefix in ('01','dd','ee'):
    plain=prefix+secrets.token_hex(15)
    selected=module.options({**cfg,'proxy_secret':plain})['connection']
    assert selected is module.ConnectionTcpMTProxyPlain
    assert issubclass(selected,connection.ConnectionTcpMTProxyAbridged)
    assert selected.normalize_secret(plain)==bytes.fromhex(plain)
    assert module.options({**cfg,'proxy_type':'webproxy','proxy_secret':plain,'webproxy_address':'proxy.example.org'})['connection'] is ConnectionWebProxy
assert module.options({**cfg,'proxy_type':'webproxy','webproxy_address':'https://PROXY.example.org'})['connection'] is ConnectionWebProxy
assert module.destination({**cfg,'chat_id':'-1000000000123','chat_access_hash':'456'})==types.InputPeerChannel(123,0)
assert module.destination({**cfg,'chat_id':'79419177'})==types.InputPeerUser(79419177,0)
assert module.destination({**cfg,'chat_id':'-1000000000123'})==types.InputPeerChannel(123,0)
assert module.destination({**cfg,'chat_id':'-123'})==types.InputPeerChat(123)
seen=[]
class FakeClient:
    def __init__(self,*args,**kwargs):seen.append(kwargs)
    async def start(self,**kwargs):assert kwargs['bot_token']==cfg['bot_token']
    async def get_input_entity(self,entity):return types.InputPeerSelf()
    async def __call__(self,request):seen.append(request)
    async def disconnect(self):seen.append('disconnected')
data={'config':cfg,'text':'Local transport check','delivery_id':str(uuid.uuid4())}
asyncio.run(module.deliver(data,FakeClient));request=seen[-2]
assert request.message=='Local transport check' and request.reply_to.reply_to_msg_id==42
assert seen[-1]=='disconnected'
ee='ee'+secrets.token_hex(16)+'front.example.org'.encode().hex()
from faketls import ConnectionTcpMTProxyFakeTLS
assert module.options({**cfg,'proxy_secret':ee})['connection'] is ConnectionTcpMTProxyFakeTLS
try:module.options({**cfg,'proxy_secret':ee,'proxy_type':'webproxy','webproxy_address':'proxy.example.org'});raise AssertionError('WEB accepted ee')
except ValueError:pass
for mode in ['mtproto','webproxy']:
    bad={**cfg,'proxy_type':mode,'proxy_secret':'ee'+secrets.token_hex(16),'webproxy_address':'proxy.example.org'}
    try:module.options(bad);raise AssertionError('accepted FakeTLS secret')
    except ValueError:pass
assert module.error_code(ConnectionError('password=do-not-print'))=='proxy'
print('PASS: real MTProto/WEB connector selection, in-memory sessions, destination/topic mapping, bounded delivery and safe error classification')
