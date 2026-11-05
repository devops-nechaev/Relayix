# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
import struct
import os
import random
import hmac
import hashlib
import time

from ..configuration import MAX_GREASE
from ..crypto import (
    generate_public_key,
    generate_key_ml_kem_768,
    to_int32
)
from ..configuration import DIGEST_OFFSET, DIGEST_LENGTH

from .op import Op
from .sequence import build_hello_op_sequence


class TlsHello:
    """
    ClientHello builder -- ConnectionSocket.cpp:149-447.

    One instance per connection: the GREASE table is drawn in the constructor
    and the op list is walked once by build().
    """

    def __init__(self, domain: str = ""):
        self.domain = domain
        self.ops = build_hello_op_sequence()
        self._scope_offsets = []
        self.grease = self._generate_grease()

    @staticmethod
    def _generate_grease() -> bytearray:
        """
        ConnectionSocket.cpp:152-162 -- the GREASE value table.

        RFC 8701 GREASE values are the 16 codepoints 0x0A0A, 0x1A1A, ...,
        0xFAFA: both bytes equal, low nibble 0xA. tgnet keeps one byte per
        slot and writes it twice (:390-391).

          - `(b & 0xf0) + 0x0A` snaps a random byte onto that ladder (:155).
          - Adjacent pairs are forced to differ (:157-161) because Chrome uses
            distinct GREASE values in the two halves of a pair (e.g. the
            cipher-suite GREASE and the extension GREASE), and matching values
            would be an anomalous fingerprint.

        NOTE ON A BOUNDS BUG: the C++ loop is
            for (size_t i = 1; i < MAX_GREASE; i += 2)
                if (grease[i] == grease[i + 1]) grease[i] ^= 0x10;
        With MAX_GREASE == 8 the last iteration is i = 7, which reads
        grease[8] -- one past the end of `uint8_t grease[8]`. So whether
        grease[7] gets flipped depends on adjacent stack memory.

        This is unobservable on the wire: the template only uses seeds
        0, 2, 3, 4 and 6, so grease[7] is never serialized. We therefore run
        the loop over i = 1, 3, 5 only, which is identical in output and
        stays in bounds.
        """
        grease = bytearray(os.urandom(MAX_GREASE))
        for a in range(MAX_GREASE):
            grease[a] = (grease[a] & 0xF0) + 0x0A
        for i in range(1, MAX_GREASE - 1, 2):
            if grease[i] == grease[i + 1]:
                grease[i] ^= 0x10
        return grease

    def build(self) -> bytearray:
        """
        ConnectionSocket.cpp:339-345 -- serialize the whole op list.

        Returns the ClientHello with the `random` field still zeroed; the
        caller patches in the HMAC digest.
        """
        out = bytearray()
        for op in self.ops:
            self._write_op(op, out)
        if self._scope_offsets:
            raise RuntimeError("unbalanced TLS hello scopes")
        return out

    def _write_op(self, op, out: bytearray):
        """
        ConnectionSocket.cpp:357-446 -- the op interpreter.

        The C++ version writes into a preallocated buffer and tracks `offset`
        by reference. Appending to a bytearray is equivalent, with
        len(out) standing in for `offset`.
        """
        t = op.type

        if t == Op.STRING:  # :360-363
            out += op.data

        elif t == Op.RANDOM:  # :364-367
            out += os.urandom(op.length)

        elif t == Op.K:  # :368-371
            out += generate_public_key()

        elif t == Op.M:  # :372-375
            out += generate_key_ml_kem_768()

        elif t == Op.ZERO:  # :376-379
            out += b"\x00" * op.length

        elif t == Op.DOMAIN:  # :380-388
            # :382-384 -- truncated at 253, the DNS name length limit
            if isinstance(self.domain, str):
                try:
                    data = self.domain.encode("idna")
                except UnicodeError:
                    data = self.domain.encode("ascii", errors="ignore")
            else:
                data = self.domain
            out += data[:253]

        elif t == Op.GREASE:  # :389-394
            g = self.grease[op.seed]
            out += bytes((g, g))

        elif t == Op.BEGIN_SCOPE:  # :395-398
            # Reserve 2 bytes; EndScope back-patches them
            self._scope_offsets.append(len(out))
            out += b"\x00\x00"

        elif t == Op.END_SCOPE:  # :399-406
            begin = self._scope_offsets.pop()
            size = len(out) - begin - 2
            out[begin] = (size >> 8) & 0xFF
            out[begin + 1] = size & 0xFF

        elif t == Op.E:  # :407-415
            # ECH payload: one of four plausible AEAD ciphertext sizes
            length = (144, 176, 208, 240)[random.randrange(4)]
            out += os.urandom(length)

        elif t == Op.P:  # :416-425
            # Pad the hello out to exactly 517 bytes, the size Chrome emits
            # when it has no post-quantum keyshare. 517 = 512 + 5 (record
            # header), and 513 here is 517 minus the 4-byte padding extension
            # header, so `zero(513 - length)` lands the total on 517.
            #
            # With ML-KEM-768 present the hello is already ~1.9 KB, so this
            # branch never fires in practice -- matching Chrome, which also
            # drops the padding once the keyshare is large. Ported for
            # fidelity: it would apply if the template ever loses the M op.
            length = len(out)
            if length <= 513:
                self._write_op(Op.string(b"\x00\x15"), out)
                self._write_op(Op.begin_scope(), out)
                self._write_op(Op.zero(513 - length), out)
                self._write_op(Op.end_scope(), out)

        elif t == Op.PERMUTATION:  # :426-443
            # Fisher-Yates over whole extension blocks (:432-437):
            #   for i in [0, n-1): j = i + rand() % (n - i); swap(i, j)
            # Note the bound is size-1, so the final element is never the
            # `i` of a swap -- it can still be swapped *into* by an earlier
            # iteration. Chrome permutes its extensions the same way, so a
            # fixed order would itself be a fingerprint.
            items = list(op.entities)
            size = len(items)
            for i in range(size - 1):
                j = i + random.randrange(size - i)
                if i != j:
                    items[i], items[j] = items[j], items[i]
            for part in items:
                for sub_op in part:
                    self._write_op(sub_op, out)

        else:
            raise ValueError("unknown TLS hello op: %r" % (t,))


def build_client_hello(
        secret: bytes,
        domain: str,
        current_time: int = None
) -> bytes:
    """
    ConnectionSocket.cpp:919-941 -- a complete, authenticated ClientHello.

    Three steps:

    1. Serialize the template with `random` zeroed (:923-925).

    2. digest = HMAC-SHA256(secret, hello) (:927). Keying on the 16-byte proxy
       secret is what makes this authentication: only a server holding the
       same secret can recompute it, and a real TLS server never would.

    3. XOR the last 4 bytes of the digest with the current unix time
       (:929-931), then write the digest over the `random` field (:933).
       The timestamp is what stops replay: the proxy checks it against its own
       clock and rejects stale hellos. The server recovers it by XORing the
       digest it computes itself against the bytes it received.

       The C++ does this as `((int32_t*)(digest+28))[0] ^= currentTime`, so it
       is a native-endian int32 XOR. Android is little-endian on every
       supported ABI, hence '<i'. A signed 32-bit pack also means the time
       wraps in 2038 the same way tgnet's does -- reproduced deliberately
       rather than widened, so the bytes match.

    Args:
        secret: the 16-byte key, i.e. secret[1:17] of the full 0xee secret
        domain: SNI hostname, i.e. secret[17:] decoded
        current_time: unix seconds; defaults to now

    Returns:
        The ClientHello bytes, ready to send, with the digest in place.
    """
    if current_time is None:
        # ConnectionSocket.cpp:929 -- ConnectionsManager::getCurrentTime(),
        # which is unix seconds adjusted by the server time offset. Local
        # time is close enough for the proxy's tolerance window.
        current_time = int(time.time())

    hello = TlsHello(domain).build()

    # ConnectionSocket.cpp:927
    digest = bytearray(hmac.new(secret, bytes(hello), hashlib.sha256).digest())

    # ConnectionSocket.cpp:930-931 -- XOR the trailing int32 with the time
    old = struct.unpack_from("<i", digest, 28)[0]
    struct.pack_into("<i", digest, 28, to_int32(old ^ to_int32(current_time)))

    # ConnectionSocket.cpp:933
    hello[DIGEST_OFFSET : DIGEST_OFFSET + DIGEST_LENGTH] = digest
    return bytes(hello)
