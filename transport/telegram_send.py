# SPDX-License-Identifier: Apache-2.0
"""One bounded MTProto delivery. Secrets arrive on stdin, never argv or disk."""
import asyncio
import json
import logging
import sys
import uuid
from urllib.parse import urlsplit
from telethon import TelegramClient, connection, functions, types, errors
from telethon.sessions import MemorySession
from telethon_webproxy import ConnectionWebProxy
from faketls import ConnectionTcpMTProxyFakeTLS, parse_secret

logging.disable(logging.CRITICAL)


def options(cfg):
    secret = cfg['proxy_secret']
    if secret.startswith('ee'):
        parse_secret(secret)
        if cfg['proxy_type'] != 'mtproto':
            raise ValueError('WEB-proxy does not support FakeTLS')
        return {'connection': ConnectionTcpMTProxyFakeTLS, 'proxy': (cfg['proxy_host'].strip('[]'), int(cfg['proxy_port']), secret)}
    if len(secret) not in (32, 34) or len(secret) == 34 and not secret.startswith('dd'):
        raise ValueError('Unsupported proxy secret')
    bytes.fromhex(secret)
    if cfg['proxy_type'] == 'mtproto':
        mode = connection.ConnectionTcpMTProxyRandomizedIntermediate if secret.startswith('dd') else connection.ConnectionTcpMTProxyAbridged
        return {'connection': mode, 'proxy': (cfg['proxy_host'].strip('[]'), int(cfg['proxy_port']), secret)}
    if cfg['proxy_type'] == 'webproxy':
        url = urlsplit('https://' + cfg['webproxy_address'].removeprefix('https://'))
        if not url.hostname or url.path not in ('', '/') or url.port or url.query or url.fragment or url.username:
            raise ValueError('WEB-proxy requires a root HTTPS hostname')
        return {'connection': ConnectionWebProxy, 'proxy': (url.hostname.encode('idna').decode().lower(), secret, {'mode': 'websocket'})}
    raise ValueError('MTProto transport requires an explicit proxy')


def destination(cfg):
    target = str(cfg['chat_id']).strip()
    if target.startswith('@'):
        return target
    chat = int(target)
    # Telegram bots use a zero access hash when no session-local full hash exists.
    # https://core.telegram.org/api/peers#access-hash
    if chat < -1000000000000:
        return types.InputPeerChannel(-chat - 1000000000000, 0)
    if chat < 0:
        return types.InputPeerChat(-chat)
    return types.InputPeerUser(chat, 0)


async def deliver(data, factory=TelegramClient):
    cfg = data['config']
    client = factory(MemorySession(), int(cfg['api_id']), cfg['api_hash'],
                     **options(cfg), timeout=10, connection_retries=1, request_retries=0,
                     auto_reconnect=False, receive_updates=False, flood_sleep_threshold=0)
    try:
        await client.start(bot_token=cfg['bot_token'])
        peer = await client.get_input_entity(destination(cfg))
        topic = cfg.get('message_thread_id')
        reply = types.InputReplyToMessage(reply_to_msg_id=int(topic)) if topic else None
        random_id = int.from_bytes(uuid.UUID(data['delivery_id']).bytes[:8], 'big', signed=True)
        await client(functions.messages.SendMessageRequest(peer=peer, message=data['text'],
                     random_id=random_id, reply_to=reply, no_webpage=True))
    finally:
        await client.disconnect()


def error_code(exc):
    if isinstance(exc, errors.FloodWaitError):
        return 'flood'
    if isinstance(exc, (errors.ApiIdInvalidError, errors.AccessTokenInvalidError, errors.AccessTokenExpiredError)):
        return 'credentials'
    if isinstance(exc, (ValueError, KeyError, errors.PeerIdInvalidError, errors.UsernameNotOccupiedError)):
        return 'destination'
    if isinstance(exc, (OSError, ConnectionError, asyncio.TimeoutError)):
        return 'proxy'
    return 'delivery'


def main():
    try:
        raw = sys.stdin.buffer.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError('Request too large')
        asyncio.run(asyncio.wait_for(deliver(json.loads(raw)), timeout=45))
        print(json.dumps({'ok': True}))
    except Exception as exc:
        # Never echo Telegram/proxy exception strings, tokens, URLs or configuration.
        print(json.dumps({'ok': False, 'code': error_code(exc)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
