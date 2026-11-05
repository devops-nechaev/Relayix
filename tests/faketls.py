"""FakeTLS wire test with an authenticated local peer; no Telegram access."""
import asyncio,hashlib,hmac,logging,secrets,struct,sys,time
sys.path.insert(0,'/app/transport')
from collections import defaultdict
from faketls import ConnectionTcpMTProxyFakeTLS,parse_secret

async def scenario(tamper=False, prefix=0x01):
    key=bytes([prefix])+secrets.token_bytes(15);domain='front.example.org'
    secret='ee'+key.hex()+domain.encode().hex()
    completed=asyncio.get_running_loop().create_future()
    payload=secrets.token_bytes(8192)
    async def peer(reader,writer):
        try:
            header=await reader.readexactly(5)
            assert header[:3]==b'\x16\x03\x01'
            hello=bytearray(header+await reader.readexactly(int.from_bytes(header[3:],'big')))
            assert domain.encode() in hello
            random=bytes(hello[11:43]);hello[11:43]=bytes(32)
            digest=hmac.new(key,hello,hashlib.sha256).digest()
            assert hmac.compare_digest(random[:28],digest[:28])
            stamp=int.from_bytes(random[28:],'little')^int.from_bytes(digest[28:],'little')
            assert abs(stamp-int(time.time()))<10
            body=b'\x02'+bytes(3)+b'\x03\x03'+bytes(32)+secrets.token_bytes(16)
            response=bytearray(b'\x16\x03\x03'+len(body).to_bytes(2,'big')+body+b'\x14\x03\x03\x00\x01\x01'+b'\x17\x03\x03\x00\x20'+secrets.token_bytes(32))
            signature=hmac.new(key,random+response,hashlib.sha256).digest()
            response[11:43]=bytes(32) if tamper else signature
            writer.write(response);await writer.drain()
            if tamper:
                assert await reader.read()==b''
            else:
                assert await reader.readexactly(6)==b'\x14\x03\x03\x00\x01\x01'
                header=await reader.readexactly(5);assert header[:3]==b'\x17\x03\x03'
                obfuscated=await reader.readexactly(int.from_bytes(header[3:],'big'));assert len(obfuscated)==64
                result=bytearray()
                while len(result)<len(payload):
                    header=await reader.readexactly(5);assert header[:3]==b'\x17\x03\x03'
                    result.extend(await reader.readexactly(int.from_bytes(header[3:],'big')))
                assert bytes(result)==payload
                for chunk in [payload[:100],payload[100:]]:
                    writer.write(b'\x17\x03\x03'+len(chunk).to_bytes(2,'big')+chunk)
                await writer.drain()
            completed.set_result(True)
        except Exception as error:
            if not completed.done():completed.set_exception(error)
        finally:
            writer.close();await writer.wait_closed()
    server=await asyncio.start_server(peer,'127.0.0.1',0)
    port=server.sockets[0].getsockname()[1]
    client=ConnectionTcpMTProxyFakeTLS('ignored.invalid',1,2,loggers=defaultdict(lambda:logging.getLogger('test')),proxy=('127.0.0.1',port,secret))
    try:
        if tamper:
            try:await client._connect(timeout=3);raise AssertionError('Accepted invalid server HMAC')
            except OSError:pass
        else:
            await client._connect(timeout=3)
            client._writer.write(payload);await client._writer.drain()
            assert await client._reader.readexactly(len(payload))==payload
            client._writer.close();await client._writer.wait_closed()
        await asyncio.wait_for(completed,3)
    finally:
        server.close();await server.wait_closed()
for prefix in (0x01, 0xdd, 0xee):
    asyncio.run(scenario(prefix=prefix))
asyncio.run(scenario(tamper=True))
for invalid in ['ee'+secrets.token_hex(16),'ee'+secrets.token_hex(16)+'bad/path'.encode().hex()]:
    try:parse_secret(invalid);raise AssertionError('Invalid secret accepted')
    except ValueError:pass
print('PASS: ee ClientHello SNI/HMAC/time, authenticated server handshake, TLS record fragmentation/reassembly tamper rejection without fallback, and dd/ee-prefixed key preservation')
