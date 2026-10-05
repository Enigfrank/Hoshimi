"""官方资源 CDN 的 HTTPS 隧道，保留客户端与官方之间的 TLS 握手。"""

import asyncio
from urllib.parse import urlsplit

from config import RESOURCE_DOWNLOAD_URL


def is_resource_cdn(authority: str) -> bool:
    """仅允许配置的 HTTPS 资源域名及 443 端口使用直通隧道。"""
    configured = urlsplit(RESOURCE_DOWNLOAD_URL)
    try:
        target = urlsplit('//' + authority)
        return (configured.scheme == 'https' and target.hostname == configured.hostname
                and target.port == 443 and not target.username and not target.password
                and not target.path and not target.query and not target.fragment)
    except ValueError:
        return False


async def relay_bytes(reader, writer):
    """原样传输 TLS 字节并传递半关闭，使客户端仍可接收完整响应。"""
    while data := await reader.read(64 * 1024):
        writer.write(data)
        await writer.drain()
    if writer.can_write_eof():
        writer.write_eof()
        await writer.drain()


async def tunnel_resource_cdn(authority: str, reader, writer):
    """连接官方 443 后建立 CONNECT 隧道，不使用本地证书解密资源请求。"""
    if not is_resource_cdn(authority):
        raise ValueError('不是允许直通的资源 CDN')
    host = urlsplit('//' + authority).hostname
    try:
        upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(host, 443), 15)
    except (OSError, TimeoutError):
        writer.write(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        await writer.drain()
        return
    pumps = []
    try:
        writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await writer.drain()
        print(f'[CDN 直通] {host}:443，使用官方 TLS 证书')
        pumps = [asyncio.create_task(relay_bytes(reader, upstream_writer)),
                 asyncio.create_task(relay_bytes(upstream_reader, writer))]
        await asyncio.gather(*pumps)
    finally:
        for pump in pumps:
            if not pump.done():
                pump.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)
        upstream_writer.close()
        await upstream_writer.wait_closed()
