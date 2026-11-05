# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
from .op import Op


def build_hello_op_sequence():
    """
    ConnectionSocket.cpp:254-337 -- the ClientHello template.

    This is a byte-for-byte transcription of a Chrome TLS 1.3 ClientHello.
    Reading the outer frame:

        16 03 01            handshake record, legacy version 0x0301
        <scope>             record length, patched by EndScope
          01 00             handshake type client_hello + length high byte
          <scope>           handshake length (low 2 of 3 bytes)
            03 03           client_version = TLS 1.2
            zero(32)        random -- overwritten later with the HMAC digest
            20 random(32)   legacy_session_id: 32 random bytes
            00 20 ...       cipher suites: 32 bytes, GREASE first
            01 00           compression: null
            <scope>         extensions length
              ...extensions...

    The `01 00` at :260 is a deliberate straddle: 0x01 is the client_hello
    handshake type and 0x00 is the high byte of the 3-byte handshake length,
    which lets a single 2-byte scope cover the remaining length bytes.
    """
    return [
        Op.string(b"\x16\x03\x01"),
        Op.begin_scope(),
        Op.string(b"\x01\x00"),
        Op.begin_scope(),
        Op.string(b"\x03\x03"),
        # ConnectionSocket.cpp:263 -- zeroed now, HMAC digest patched in later
        Op.zero(32),
        Op.string(b"\x20"),
        Op.random(32),
        Op.string(b"\x00\x20"),
        Op.grease(0),
        # ConnectionSocket.cpp:268 -- cipher suites then `01 00` compression
        Op.string(
            b"\x13\x01\x13\x02\x13\x03\xc0\x2b\xc0\x2f\xc0\x2c\xc0\x30"
            b"\xcc\xa9\xcc\xa8\xc0\x13\xc0\x14\x00\x9c\x00\x9d\x00\x2f"
            b"\x00\x35\x01\x00"
        ),
        Op.begin_scope(),
        Op.grease(2),
        Op.string(b"\x00\x00"),
        # ConnectionSocket.cpp:272-326 -- extensions, order randomized per
        # connection so the fingerprint matches Chrome's own shuffling
        Op.permutation(
            [
                # server_name (0x0000): nested scopes give list length, then
                # entry length, around the domain from the proxy secret
                [
                    Op.string(b"\x00\x00"),
                    Op.begin_scope(),
                    Op.begin_scope(),
                    Op.string(b"\x00"),
                    Op.begin_scope(),
                    Op.domain(),
                    Op.end_scope(),
                    Op.end_scope(),
                    Op.end_scope(),
                ],
                # status_request (0x0005)
                [Op.string(b"\x00\x05\x00\x05\x01\x00\x00\x00\x00")],
                # supported_groups (0x000a): GREASE, 0x11ec (X25519MLKEM768),
                # 0x001d (x25519), 0x0017 (secp256r1), 0x0018 (secp384r1)
                [
                    Op.string(b"\x00\x0a\x00\x0c\x00\x0a"),
                    Op.grease(4),
                    Op.string(b"\x11\xec\x00\x1d\x00\x17\x00\x18"),
                ],
                # ec_point_formats (0x000b)
                [Op.string(b"\x00\x0b\x00\x02\x01\x00")],
                # signature_algorithms (0x000d)
                [
                    Op.string(
                        b"\x00\x0d\x00\x12\x00\x10\x04\x03\x08\x04\x04\x01"
                        b"\x05\x03\x08\x05\x05\x01\x08\x06\x06\x01"
                    )
                ],
                # ALPN (0x0010): h2, http/1.1
                [
                    Op.string(
                        b"\x00\x10\x00\x0e\x00\x0c\x02\x68\x32\x08\x68\x74"
                        b"\x74\x70\x2f\x31\x2e\x31"
                    )
                ],
                # signed_certificate_timestamp (0x0012)
                [Op.string(b"\x00\x12\x00\x00")],
                # extended_master_secret (0x0017)
                [Op.string(b"\x00\x17\x00\x00")],
                # compress_certificate (0x001b): brotli
                [Op.string(b"\x00\x1b\x00\x03\x02\x00\x02")],
                # session_ticket (0x0023)
                [Op.string(b"\x00\x23\x00\x00")],
                # supported_versions (0x002b): GREASE, TLS 1.3, TLS 1.2
                [
                    Op.string(b"\x00\x2b\x00\x07\x06"),
                    Op.grease(6),
                    Op.string(b"\x03\x04\x03\x03"),
                ],
                # psk_key_exchange_modes (0x002d)
                [Op.string(b"\x00\x2d\x00\x02\x01\x01")],
                # key_share (0x0033): GREASE entry (1 byte), then 0x11ec
                # X25519MLKEM768 with a 0x04c0 = 1216-byte share
                # (1184 ML-KEM + 32 X25519), then 0x001d x25519 with 32 bytes
                [
                    Op.string(b"\x00\x33\x04\xef\x04\xed"),
                    Op.grease(4),
                    Op.string(b"\x00\x01\x00\x11\xec\x04\xc0"),
                    Op.m(),
                    Op.k(),
                    Op.string(b"\x00\x1d\x00\x20"),
                    Op.k(),
                ],
                # application_settings (0x44cd): h2
                [Op.string(b"\x44\xcd\x00\x05\x00\x03\x02\x68\x32")],
                # encrypted_client_hello (0xfe0d): outer, AES-128-GCM,
                # 32-byte config id, then a variable-length payload
                [
                    Op.string(b"\xfe\x0d"),
                    Op.begin_scope(),
                    Op.string(b"\x00\x00\x01\x00\x01"),
                    Op.random(1),
                    Op.string(b"\x00\x20"),
                    Op.random(32),
                    Op.begin_scope(),
                    Op.e(),
                    Op.end_scope(),
                    Op.end_scope(),
                ],
                # renegotiation_info (0xff01)
                [Op.string(b"\xff\x01\x00\x01\x00")],
            ]
        ),
        # ConnectionSocket.cpp:327-329 -- trailing GREASE extension, 1 zero byte
        Op.grease(3),
        Op.string(b"\x00\x01\x00"),
        Op.p(),
        Op.end_scope(),
        Op.end_scope(),
        Op.end_scope(),
    ]
