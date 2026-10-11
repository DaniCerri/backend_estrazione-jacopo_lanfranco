"""Avvio di produzione: un solo socket dual-stack IPv4 + IPv6.

uvicorn --host :: ascolta solo IPv6 (asyncio imposta IPV6_V6ONLY), mentre serve
IPv6 per la rete privata Railway (*.railway.internal) e IPv4 per tutto il resto.
"""

import os
import socket

import uvicorn


def _socket(porta: int) -> socket.socket:
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        indirizzo: tuple = ("::", porta)
    except OSError:
        # IPv6 non disponibile nel container
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        indirizzo = ("0.0.0.0", porta)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(indirizzo)
    return sock


def main() -> None:
    porta = int(os.environ.get("PORT", "8000"))
    server = uvicorn.Server(uvicorn.Config("app.main:app", log_level="info"))
    server.run(sockets=[_socket(porta)])


if __name__ == "__main__":
    main()
