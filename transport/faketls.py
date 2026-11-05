# SPDX-License-Identifier: Apache-2.0
"""Authenticated ee transport for Telethon, with no non-TLS fallback."""
import asyncio
import re
from telethon.network.connection.connection import ObfuscatedConnection
from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate
from vendor.faketls.client_hello import build_client_hello
from vendor.faketls.server_hello import read_server_hello
from vendor.faketls.record_layer import TlsRecordLayer


def parse_secret(encoded):
    try:
        raw = bytes.fromhex(encoded)
    except (TypeError, ValueError):
        raise ValueError('Invalid FakeTLS secret') from None
    if len(raw) <= 17 or raw[0] != 0xee:
        raise ValueError('FakeTLS requires an ee marker, 16-byte key and SNI domain')
    try:
        domain = raw[17:].decode('ascii')
    except UnicodeDecodeError:
        raise ValueError('FakeTLS SNI must be an ASCII DNS name') from None
    if len(domain) > 253 or not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}', domain):
        raise ValueError('FakeTLS SNI must be an ASCII DNS name')
    return raw[1:17], domain


class ConnectionTcpMTProxyFakeTLS(ConnectionTcpMTProxyRandomizedIntermediate):
    def __init__(self, ip, port, dc_id, *, loggers, proxy=None, local_addr=None):
        if not proxy or len(proxy) != 3:
            raise ValueError('FakeTLS requires an explicit proxy')
        self._tls_key, self._tls_domain = parse_secret(proxy[2])
        super().__init__(ip, port, dc_id, loggers=loggers,
                         # Telethon strips a leading dd/ee marker from hex strings. Always
                         # supply the randomized-intermediate marker so all 16 key bytes survive.
                         proxy=(proxy[0], proxy[1], 'dd' + self._tls_key.hex()), local_addr=local_addr)

    async def _connect(self, timeout=None, ssl=None):
        writer = None
        async def handshake():
            nonlocal writer
            reader, writer = await asyncio.open_connection(self._ip, self._port, local_addr=self._local_addr)
            hello = build_client_hello(self._tls_key, self._tls_domain)
            writer.write(hello)
            await writer.drain()
            await read_server_hello(reader, self._tls_key, hello)
            records = TlsRecordLayer(reader, writer)
            self._reader = records
            self._writer = records
            self._codec = self.packet_codec(self)
            ObfuscatedConnection._init_conn(self)
            await records.drain()
        try:
            await asyncio.wait_for(handshake(), timeout=timeout or 10)
        except BaseException:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
            raise
