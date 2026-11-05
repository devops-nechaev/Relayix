# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
import asyncio
import hashlib
import hmac

from .configuration import (
    RECORD_SERVER_HANDSHAKE,
    MAX_HANDSHAKE_BYTES,
    RECORD_SERVER_CCS_THEN_DATA,
    DIGEST_OFFSET,
    DIGEST_LENGTH
)

from .errors import TgNetTlsHandshakeError


async def read_server_hello(reader, secret: bytes, client_hello: bytes) -> None:
    """
    ConnectionSocket.cpp:715-782 -- read and verify the server's response.

    The server sends three records back to back:

        16 03 03 <len1>  <len1 bytes>    ServerHello
        14 03 03 00 01 01                ChangeCipherSpec
        17 03 03 <len2>  <len2 bytes>    ApplicationData (decorative filler)

    tgnet accumulates until it has all of them -- the wait condition at :754 is
    `newBytesRead < len2 + len1 + 5 + 11`, i.e. 5 header + len1 + 9 CCS-plus-
    header + 2 length + len2 -- then HMACs the lot. Because asyncio gives us
    readexactly(), we can read each piece by length instead of re-parsing a
    growing buffer, which is the same computation without the accumulator.

    Verification (:759-773):
        server_random = response[11:43]
        response[11:43] = 0
        expected = HMAC-SHA256(secret, client_digest || response)
        require expected == server_random

    Chaining the client digest into the server's HMAC binds the response to
    this specific ClientHello, so a recorded server reply cannot be replayed
    against a fresh client.

    The ApplicationData record here is TLS-shaped padding, not MTProto: at
    :774-778 tgnet advances state and drops the buffer without calling
    onReceivedData. It can be discarded safely because the server has not yet
    seen the obfuscated header, so it cannot have sent MTProto data.

    Raises:
        TgNetTlsHandshakeError: framing wrong, or digest mismatch
    """
    try:
        # ConnectionSocket.cpp:723-732 -- record 1 header
        header = await reader.readexactly(5)
        if header[:3] != RECORD_SERVER_HANDSHAKE:
            raise TgNetTlsHandshakeError(
                "TLS hello1 mismatch: expected %r, got %r "
                "(ConnectionSocket.cpp:726-731)"
                % (RECORD_SERVER_HANDSHAKE, bytes(header[:3]))
            )

        len1 = (header[3] << 8) | header[4]
        # ConnectionSocket.cpp:733 -- reject before allocating
        if len1 > MAX_HANDSHAKE_BYTES - 5:
            raise TgNetTlsHandshakeError(
                "TLS len1 invalid: %d (ConnectionSocket.cpp:733)" % len1
            )

        server_hello_body = await reader.readexactly(len1)

        # ConnectionSocket.cpp:743-748 -- CCS plus the next record's type/version
        ccs_and_type = await reader.readexactly(len(RECORD_SERVER_CCS_THEN_DATA))
        if ccs_and_type != RECORD_SERVER_CCS_THEN_DATA:
            raise TgNetTlsHandshakeError(
                "TLS hello2 mismatch: expected %r, got %r "
                "(ConnectionSocket.cpp:743-747)"
                % (RECORD_SERVER_CCS_THEN_DATA, bytes(ccs_and_type))
            )

        # ConnectionSocket.cpp:749-753 -- record 3 length
        len2_bytes = await reader.readexactly(2)
        len2 = (len2_bytes[0] << 8) | len2_bytes[1]
        if len2 > MAX_HANDSHAKE_BYTES - len1 - 5 - 11:
            raise TgNetTlsHandshakeError(
                "TLS len2 invalid: %d (ConnectionSocket.cpp:750)" % len2
            )

        filler = await reader.readexactly(len2)
    except asyncio.IncompleteReadError as e:
        raise TgNetTlsHandshakeError(
            "TLS handshake incomplete: server closed connection unexpectedly"
        ) from e

    # The exact byte range tgnet HMACs (all of newBytesRead at :766)
    response = bytearray(
        header + server_hello_body + ccs_and_type + len2_bytes + filler
    )

    # ConnectionSocket.cpp:759-760 -- save the server random, then zero it so
    # both sides HMAC the same bytes
    server_random = bytes(response[DIGEST_OFFSET : DIGEST_OFFSET + DIGEST_LENGTH])
    response[DIGEST_OFFSET : DIGEST_OFFSET + DIGEST_LENGTH] = b"\x00" * DIGEST_LENGTH

    # ConnectionSocket.cpp:762-766 -- client digest prefixed to the response.
    # The digest is read back out of the ClientHello we sent, which is where
    # tgnet keeps it too (tempBuffer + 64*1024, still holding the time-XORed
    # value written at :931).
    client_digest = client_hello[DIGEST_OFFSET : DIGEST_OFFSET + DIGEST_LENGTH]
    expected = hmac.new(
        secret, client_digest + bytes(response), hashlib.sha256
    ).digest()

    # ConnectionSocket.cpp:768-773 -- tgnet compares with memcmp, which is
    # *not* constant-time: a timing leak there could expose the secret. We
    # use hmac.compare_digest instead -- same result, no leak.
    if not hmac.compare_digest(expected, server_random):
        raise TgNetTlsHandshakeError(
            "TLS hash mismatch -- wrong proxy secret or not an MTProxy "
            "(ConnectionSocket.cpp:768-772)",
            hash_mismatch=True,
        )
