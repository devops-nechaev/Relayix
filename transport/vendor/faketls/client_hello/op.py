# SPDX-License-Identifier: MIT
# Vendored from nsdkinx/tgnet; imports adapted for Relayix. See UPSTREAM.
class Op:
    """
    One instruction in the ClientHello template (ConnectionSocket.cpp:164-252).

    tgnet describes the ClientHello as a flat op list rather than a struct
    tree. That buys two things a struct could not do cleanly: length fields
    can be back-patched by scope ops, and whole extension blocks can be
    permuted as opaque units.

    Types (ConnectionSocket.cpp:166):
        String       literal bytes
        Random       n cryptographically random bytes
        K            32-byte X25519 public key
        M            1184-byte ML-KEM-768 key
        P            padding extension sizing the hello to 517 bytes
        E            random 144/176/208/240 bytes (ECH-shaped payload)
        Zero         n zero bytes
        Domain       the SNI hostname from the proxy secret
        Grease       one GREASE value written twice
        BeginScope   reserve 2 bytes for a length, to be patched
        EndScope     patch the matching reserved length
        Permutation  shuffle a list of op-sequences, then emit them
    """

    STRING = "String"
    RANDOM = "Random"
    K = "K"
    M = "M"
    P = "P"
    E = "E"
    ZERO = "Zero"
    DOMAIN = "Domain"
    GREASE = "Grease"
    BEGIN_SCOPE = "BeginScope"
    END_SCOPE = "EndScope"
    PERMUTATION = "Permutation"

    __slots__ = ("type", "length", "seed", "data", "entities")

    def __init__(self, type_, length=0, seed=0, data=b"", entities=None):
        self.type = type_
        self.length = length
        self.seed = seed
        self.data = data
        self.entities = entities or []

    # Factory helpers mirroring ConnectionSocket.cpp:174-250
    @staticmethod
    def string(data):
        return Op(Op.STRING, data=data)

    @staticmethod
    def random(length):
        return Op(Op.RANDOM, length=length)

    @staticmethod
    def k():
        return Op(Op.K, length=32)  # ConnectionSocket.cpp:191

    @staticmethod
    def m():
        return Op(Op.M)

    @staticmethod
    def p():
        return Op(Op.P)

    @staticmethod
    def e():
        return Op(Op.E)

    @staticmethod
    def zero(length):
        return Op(Op.ZERO, length=length)

    @staticmethod
    def domain():
        return Op(Op.DOMAIN)

    @staticmethod
    def grease(seed):
        return Op(Op.GREASE, seed=seed)

    @staticmethod
    def begin_scope():
        return Op(Op.BEGIN_SCOPE)

    @staticmethod
    def end_scope():
        return Op(Op.END_SCOPE)

    @staticmethod
    def permutation(entities):
        return Op(Op.PERMUTATION, entities=entities)
