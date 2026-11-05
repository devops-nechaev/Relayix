# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
import os
import struct

from .configuration import P25519, P25519_LEGENDRE_POW, CURVE_A


def get_y2(x: int, mod: int = P25519) -> int:
    """
    ConnectionSocket.cpp:41-54 -- y^2 = x^3 + 486662*x^2 + x (mod p)

    The C++ version evaluates it Horner-style to keep the BIGNUM count down:
        y = x; y += A; y *= x; y += 1; y *= x
    which expands to ((x + A) * x + 1) * x. Same polynomial, fewer temporaries.
    """
    return (((x + CURVE_A) % mod) * x + 1) % mod * x % mod


def get_double_x(x: int, mod: int = P25519) -> int:
    """
    ConnectionSocket.cpp:56-77 -- x-coordinate of 2*P, given only x.

        x_2 = (x^2 - 1)^2 / (4 * y^2)

    This is the standard Montgomery x-only doubling formula. Working purely in
    x avoids ever computing y, which is why the code only needs the quadratic
    residue *test* above and not an actual square root.
    """
    denominator = (4 * get_y2(x, mod)) % mod
    numerator = pow((x * x - 1) % mod, 2, mod)
    return numerator * pow(denominator, -1, mod) % mod


def generate_public_key() -> bytes:
    """
    ConnectionSocket.cpp:98-147 -- a random, plausible X25519 public key.

    This is *not* a real keypair: no private scalar is ever kept, because
    nothing performs a key exchange. It only has to be a valid point that a
    fingerprinting middlebox would accept.

    The construction:
      1. 32 random bytes with the top bit cleared (:108-109), interpreted
         big-endian, then squared mod p (:112). Squaring guarantees the value
         is a quadratic residue in x, which biases the search below.
      2. Reject until y^2 = f(x) is itself a quadratic residue (:114-124), so
         x is the abscissa of a real curve point rather than a twist point.
      3. Triple x-only doubling (:127-131) multiplies the point by 8. That
         clears the cofactor, landing in the prime-order subgroup exactly like
         X25519's clamping would.
      4. Serialize big-endian, zero-padded to 32 (:133-136), then reverse the
         byte order (:137-141) because X25519 wire format is little-endian.

    NOTE: os.urandom replaces OpenSSL's RAND_bytes. Both are CSPRNGs; the
    values are decorative here in any case.
    """
    while True:
        key = bytearray(os.urandom(32))
        key[31] &= 127  # ConnectionSocket.cpp:109

        # ConnectionSocket.cpp:110 -- BN_bin2bn reads big-endian
        x = int.from_bytes(bytes(key), "big")
        x = x * x % P25519  # ConnectionSocket.cpp:112

        y2 = get_y2(x)
        # ConnectionSocket.cpp:117-122 -- BN_is_one(y2^((p-1)/2)) means y exists
        if pow(y2, P25519_LEGENDRE_POW, P25519) == 1:
            break

    # ConnectionSocket.cpp:127-131 -- multiply by 8
    for _ in range(3):
        x = get_double_x(x)

    # ConnectionSocket.cpp:133-141 -- big-endian, then byte-reversed
    return x.to_bytes(32, "big")[::-1]


def generate_key_ml_kem_768() -> bytes:
    """
    ConnectionSocket.cpp:79-96 -- a decorative ML-KEM-768 encapsulation key.

    Real ML-KEM-768 keys are 1184 bytes: 1152 bytes of packed polynomial
    coefficients plus a 32-byte seed. tgnet fabricates one that is
    *statistically* indistinguishable without doing any lattice work:

      - 768 uniform values mod Q=3329 (:87-88). Real coefficients are also
        uniform mod Q, so the marginal distribution matches.
      - 12-bit packing, two coefficients into three bytes (:90-92):
            byte0 =  a        & 0xff
            byte1 = (a >> 8) | ((b & 0x0f) << 4)
            byte2 =  b >> 4
        384 iterations * 3 = 1152 bytes.
      - 32 random bytes appended (:95) standing in for the seed.

    A middlebox cannot tell the difference: verifying a real key needs the
    matching secret, which never appears in a ClientHello.

    NOTE: `values[i] % Q` on uniform uint32 is very slightly biased (2^32 is
    not a multiple of 3329). tgnet has the same bias; it is irrelevant here
    and reproducing it keeps the byte distribution identical.
    """
    Q = 3329  # ConnectionSocket.cpp:80
    N = 384  # ConnectionSocket.cpp:81

    # ConnectionSocket.cpp:83-84 -- N*2 uint32 values, i.e. 768 coefficients
    raw = os.urandom(N * 2 * 4)
    values = struct.unpack("<%dI" % (N * 2), raw)

    key = bytearray(1184)
    for i in range(N):
        a = values[i * 2] % Q
        b = values[i * 2 + 1] % Q
        key[i * 3 + 0] = a & 0xFF
        key[i * 3 + 1] = ((a >> 8) | ((b & 0x0F) << 4)) & 0xFF
        key[i * 3 + 2] = (b >> 4) & 0xFF

    key[1152:1184] = os.urandom(32)  # ConnectionSocket.cpp:95
    return bytes(key)

def to_int32(value: int) -> int:
    """
    Wrap to a signed 32-bit int.

    C++ int32_t arithmetic wraps; Python ints are arbitrary precision, so an
    XOR of two positive values can exceed the int32 range and break the
    struct.pack. Masking to 32 bits and sign-extending reproduces the C++
    result exactly.
    """
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value

def parse_tls_secret(secret) -> tuple:
    """
    Split a fake-TLS proxy secret into its key and domain.

    ConnectionSocket.cpp:593-597:
        if (secret.size() > 17 && secret[0] == '\\xee') {
            proxyAuthState = 10;
            currentSecret = secret.substr(1, 16);
            currentSecretDomain = secret.substr(17);
        }

    Layout:
        byte 0      0xee marker
        bytes 1-16  the 16-byte shared key
        bytes 17+   the SNI domain to impersonate, as ASCII

    Note the strict `> 17`: a secret of exactly 17 bytes has an empty domain
    and does *not* enable fake-TLS. Connection.cpp:465 agrees, requiring
    `length() > 17` before selecting ProtocolTypeTLS, whereas the 0xdd check
    at :463 only needs `>= 17`.

    Args:
        secret: raw bytes, or a hex string

    Returns:
        (key_16_bytes, domain_str)

    Raises:
        ValueError: not a fake-TLS secret
    """
    if isinstance(secret, str):
        secret = bytes.fromhex(secret)

    if len(secret) <= 17 or secret[0] != 0xEE:
        raise ValueError(
            "not a fake-TLS secret: needs a 0xee marker and length > 17, "
            "got first byte %s and length %d (ConnectionSocket.cpp:593)"
            % (hex(secret[0]) if secret else "empty", len(secret))
        )

    key = secret[1:17]
    domain = secret[17:].decode("ascii", errors="replace")
    return key, domain
