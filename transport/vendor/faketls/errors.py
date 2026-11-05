class TgNetInvalidPacketError(IOError):
    """Raised when receiving an invalid packet (triggers reconnect)"""
    pass

class TgNetTlsHandshakeError(IOError):
    """
    A fake-TLS handshake failure.

    tgnet's equivalent is closeSocket(1, -1) plus, on digest mismatch only,
    tlsHashMismatch = true (ConnectionSocket.cpp:769). The flag tells
    ConnectionsManager the *secret* is wrong rather than the network: it
    feeds the disconnect-timeout budget, and once that reaches its cap tgnet
    escalates to a fresh address/port request via
    onRequestNewServerIpAndPort(requestingSecondAddress=1)
    (ConnectionsManager.cpp:699,715-721). `hash_mismatch` carries the same
    signal.
    """

    def __init__(self, message, hash_mismatch=False):
        super().__init__(message)
        self.hash_mismatch = hash_mismatch
