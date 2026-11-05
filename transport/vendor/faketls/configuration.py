# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
# ConnectionSocket.cpp:1024 -- ApplicationData record header, TLS 1.2 version
# on the wire (TLS 1.3 keeps 0x0303 for backwards compatibility)
RECORD_APPLICATION_DATA = b"\x17\x03\x03"

# ConnectionSocket.cpp:1019 -- ChangeCipherSpec, prepended to the very first
# outbound record only (tlsState 1 -> 2)
RECORD_CHANGE_CIPHER_SPEC = b"\x14\x03\x03\x00\x01\x01"

# ConnectionSocket.cpp:726 -- server handshake record prefix
RECORD_SERVER_HANDSHAKE = b"\x16\x03\x03"

# ConnectionSocket.cpp:743 -- what must directly follow the ServerHello record
RECORD_SERVER_CCS_THEN_DATA = b"\x14\x03\x03\x00\x01\x01\x17\x03\x03"

# ConnectionSocket.cpp:1014 -- outbound payload is chunked at 2878 bytes.
# 2878 + 6 (CCS) + 5 (record header) = 2889, comfortably inside one MTU-ish
# write and well under the 16384 TLS record ceiling.
MAX_RECORD_PAYLOAD = 2878

# ConnectionSocket.cpp:863,733 -- inbound length sanity limits
MAX_RECORD_LENGTH = 64 * 1024
MAX_HANDSHAKE_BYTES = 64 * 1024

# ConnectionSocket.cpp:39
MAX_GREASE = 8

# ConnectionSocket.cpp:759,933 -- the digest lives at offset 11 of the
# ClientHello / ServerHello, i.e. the TLS `random` field:
#   0..2   record type + version      (3 bytes)
#   3..4   record length              (2 bytes)
#   5      handshake type (0x01/0x02) (1 byte)
#   6..8   handshake length           (3 bytes)
#   9..10  client/server version      (2 bytes)
#   11..42 random                     (32 bytes)  <-- HMAC digest
DIGEST_OFFSET = 11
DIGEST_LENGTH = 32

# ---------------------------------------------------------------------------
# Curve25519 helpers -- ConnectionSocket.cpp:41-147
# ---------------------------------------------------------------------------

# ConnectionSocket.cpp:100 -- the Curve25519 field prime, 2^255 - 19
P25519 = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFED

# ConnectionSocket.cpp:102 -- (p-1)/2 = 2^254 - 10, the Euler's-criterion
# exponent: pow(y2, (p-1)/2, p) == 1 exactly when y2 is a quadratic residue
P25519_LEGENDRE_POW = 0x3FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF6

# ConnectionSocket.cpp:46 -- Montgomery curve coefficient A for Curve25519
CURVE_A = 486662
