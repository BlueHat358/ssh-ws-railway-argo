#!/usr/bin/env python3
"""
WebSocket <-> SSH proxy.

Menerima koneksi HTTP/WebSocket di suatu port, memvalidasi handshake
WebSocket (atau membiarkan permintaan HTTP biasa lewat sebagai "payload"
gaya bug-host / CONNECT untuk kompatibilitas dengan client HTTP Injector,
NPV Tunnel, dsb), lalu meneruskan (relay) semua data mentah ke server
SSH lokal (127.0.0.1:22).

Tidak butuh dependency luar (hanya modul standar Python), supaya build
Docker tetap ringan.
"""

import asyncio
import base64
import hashlib
import logging
import os
import signal
import sys

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("WS_PORT", "8880"))
TARGET_HOST = os.environ.get("WS_TARGET_HOST", "127.0.0.1")
TARGET_PORT = int(os.environ.get("WS_TARGET_PORT", "22"))
# Respons default yang dikirim untuk permintaan HTTP biasa (mode "payload"),
# supaya kompatibel dengan aplikasi client yang mengirim custom HTTP request
# sebelum benar-benar melakukan upgrade ke WebSocket.
DEFAULT_RESPONSE = os.environ.get(
    "WS_RESPONSE",
    "HTTP/1.1 101 Switching Protocols\r\n\r\n",
)

logging.basicConfig(
    level=logging.INFO,
    format="[ws-proxy] %(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ws-proxy")


async def read_http_headers(reader: asyncio.StreamReader) -> bytes:
    """Baca header HTTP request sampai menemukan CRLFCRLF."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(1)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    return data


def parse_headers(raw: bytes) -> dict:
    headers = {}
    try:
        lines = raw.decode(errors="ignore").split("\r\n")
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
    except Exception:
        pass
    return headers


def make_accept_key(ws_key: str) -> str:
    sha1 = hashlib.sha1((ws_key + WS_MAGIC).encode()).digest()
    return base64.b64encode(sha1).decode()


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    log.info("Koneksi masuk dari %s", peer)

    try:
        raw_headers = await read_http_headers(reader)
        headers = parse_headers(raw_headers)

        is_ws_upgrade = headers.get("upgrade", "").lower() == "websocket"

        if is_ws_upgrade and "sec-websocket-key" in headers:
            accept_key = make_accept_key(headers["sec-websocket-key"])
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n"
            )
            if "sec-websocket-protocol" in headers:
                response += f"Sec-WebSocket-Protocol: {headers['sec-websocket-protocol']}\r\n"
            response += "\r\n"
            writer.write(response.encode())
        else:
            # Mode kompatibilitas: request HTTP biasa (bukan upgrade WS resmi),
            # tetap balas 101 supaya client tunneling non-standar tetap jalan.
            writer.write(DEFAULT_RESPONSE.encode())

        await writer.drain()

        # Sambungkan ke SSH lokal
        try:
            target_reader, target_writer = await asyncio.open_connection(
                TARGET_HOST, TARGET_PORT
            )
        except Exception as e:
            log.error("Gagal konek ke target %s:%s -> %s", TARGET_HOST, TARGET_PORT, e)
            writer.close()
            return

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter):
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except (ConnectionResetError, asyncio.IncompleteReadError):
                pass
            except Exception as e:
                log.debug("pipe error: %s", e)
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        await asyncio.gather(
            pipe(reader, target_writer),
            pipe(target_reader, writer),
        )

    except Exception as e:
        log.error("Error menangani klien %s: %s", peer, e)
    finally:
        try:
            writer.close()
        except Exception:
            pass
        log.info("Koneksi %s ditutup", peer)


async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    log.info(
        "WS proxy jalan di %s:%s -> forward ke %s:%s",
        LISTEN_HOST, LISTEN_PORT, TARGET_HOST, TARGET_PORT,
    )
    async with server:
        await server.serve_forever()


def handle_sigterm(*_):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
