# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
import struct

from .errors import TgNetInvalidPacketError

from .configuration import (
    RECORD_APPLICATION_DATA,
    RECORD_CHANGE_CIPHER_SPEC,
    MAX_RECORD_LENGTH,
    MAX_RECORD_PAYLOAD
)


class TlsRecordLayer:
    """
    Chops the outbound byte stream into TLS ApplicationData records and
    reassembles the inbound one.

    Sits between the socket and the AES-CTR obfuscation, matching tgnet's
    split: the record layer is in ConnectionSocket, the obfuscation in
    Connection, so records carry already-obfuscated bytes.

    Implements the reader interface (`readexactly`) and the writer interface
    (`write`, `drain`, `close`, ...) so it can be dropped in for Telethon's
    reader/writer pair and `TgNetObfuscatedIO` keeps working untouched.

    tgnet's `tlsState` (ConnectionSocket.cpp:1018-1023):
        0  not a TLS connection
        1  handshake done, next write must carry the CCS prefix
        2  steady state
    """

    def __init__(self, reader, writer):
        self._reader = reader
        self._writer = writer
        # ConnectionSocket.cpp:775 -- tlsState = 1 after a verified handshake
        self._tls_state = 1
        # Buffered plaintext from records already read
        self._buffer = bytearray()

    # -- reading ------------------------------------------------------------

    async def readexactly(self, n: int) -> bytes:
        """
        ConnectionSocket.cpp:833-897 -- de-frame inbound records.

        tgnet's version is a state machine because recv() hands it arbitrary
        chunk boundaries: it keeps a partial header in tlsBuffer with a
        tlsBufferSized flag (:838-843, :889-895) for when fewer than 5 bytes
        of a header have arrived. asyncio's readexactly() makes the boundary
        handling implicit, so we just pull whole records until we have n bytes.

        A record's payload can span what the caller asked for, so leftovers
        stay buffered for the next call -- equivalent to tgnet's
        `restOfTheData` handling.
        """
        while len(self._buffer) < n:
            await self._read_record()

        result = bytes(self._buffer[:n])
        del self._buffer[:n]
        return result

    async def _read_record(self):
        """
        Read exactly one ApplicationData record.

        ConnectionSocket.cpp:856-871 -- the type/version prefix must be
        `17 03 03` and the length must be at most 64 KB. Anything else means
        the peer is not speaking the fake-TLS dialect, and tgnet closes the
        socket rather than trying to resynchronize.
        """
        header = await self._reader.readexactly(5)

        # ConnectionSocket.cpp:856-861
        if header[:3] != RECORD_APPLICATION_DATA:
            raise TgNetInvalidPacketError(
                "TLS response header1 mismatch: expected %r, got %r "
                "(ConnectionSocket.cpp:857-860)"
                % (RECORD_APPLICATION_DATA, bytes(header[:3]))
            )

        # ConnectionSocket.cpp:862
        length = (header[3] << 8) | header[4]

        # ConnectionSocket.cpp:863-866
        if length > MAX_RECORD_LENGTH:
            raise TgNetInvalidPacketError(
                "TLS response len1 invalid: %d exceeds 64 KB "
                "(ConnectionSocket.cpp:863-865)" % length
            )

        # A zero-length record is legal TLS but would spin this loop forever
        # without progress, so treat it as a no-op read and let the caller's
        # `while len(buffer) < n` fetch the next record.
        if length:
            self._buffer += await self._reader.readexactly(length)

    # -- writing ------------------------------------------------------------

    def write(self, data: bytes):
        """
        ConnectionSocket.cpp:1013-1044 -- frame outbound data as records.

        Two details from tgnet:

        - The first record is preceded by ChangeCipherSpec (:1018-1023). A real
          TLS 1.3 client sends CCS once, immediately after its ClientHello, as
          the "compatibility mode" middlebox appeasement. Sending it here, on
          the same write as the first application data, is what a real client's
          packet trace looks like.

        - Payloads are capped at 2878 bytes (:1014-1016). tgnet only truncates
          the current send and lets epoll re-fire for the rest; we loop, since
          asyncio buffers the whole write.
        """
        view = memoryview(data)
        offset = 0

        while offset < len(view):
            chunk = view[offset : offset + MAX_RECORD_PAYLOAD]
            offset += len(chunk)

            out = bytearray()
            # ConnectionSocket.cpp:1018-1023 -- CCS on the first record only
            if self._tls_state == 1:
                out += RECORD_CHANGE_CIPHER_SPEC
                self._tls_state = 2

            # ConnectionSocket.cpp:1024-1030
            out += RECORD_APPLICATION_DATA
            out += struct.pack(">H", len(chunk))
            out += chunk

            self._writer.write(out)

    # -- passthrough --------------------------------------------------------
    # Telethon calls these on the writer directly (connection.py:244,274,277),
    # so forward them to the real StreamWriter.

    async def drain(self):
        await self._writer.drain()

    def close(self):
        self._writer.close()

    async def wait_closed(self):
        await self._writer.wait_closed()

    def get_extra_info(self, name, default=None):
        return self._writer.get_extra_info(name, default)

    @property
    def tls_state(self):
        return self._tls_state
