import json
import hashlib
import re
from functools import lru_cache
import asyncio
from urllib.request import Request, urlopen

from config import CLIENT_VERSION_NAME, HOTFIX_BASE_URL, STREAMING_ASSETS_DIR, RESOURCE_DOWNLOAD_URL, RESOURCE_DOWNLOAD_MODE


@lru_cache(maxsize=1)
def resource_files() -> dict:
    """索引当前清单中的内容散列和大小，只转发已知资源。"""
    manifest = json.loads((STREAMING_ASSETS_DIR / 'AssetHash_Info.bytes').read_bytes())
    return {row.split('|')[1] + '.ys': int(row.split('|')[2])
            for row in manifest['assetHashList'] if row.split('|')[0].endswith('.ys')}


def remote_resource_url(filename: str) -> str | None:
    """本机缺少的有效 bundle 使用官服同版本内容散列地址按需下载。"""
    if filename in resource_files() and not (STREAMING_ASSETS_DIR / filename).is_file() \
            and not (STREAMING_ASSETS_DIR / filename[0] / filename[1] / filename).is_file():
        return RESOURCE_DOWNLOAD_URL.rstrip('/') + '/' + filename
    return None


async def stream_remote_resource(filename: str, writer, range_header: str = '') -> None:
    """分块转发官方资源，避免客户端不支持重定向或大文件占满内存。"""
    url = remote_resource_url(filename)
    if not url:
        raise ValueError('资源不在当前清单中')
    headers = {}
    if range_header:
        if not re.fullmatch(r'bytes=\d+-\d*', range_header):
            writer.write(b'HTTP/1.1 416 Range Not Satisfiable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
            return
        headers['Range'] = range_header
    response = None
    headers_sent = False
    try:
        response = await asyncio.to_thread(urlopen, Request(url, headers=headers), timeout=30)
        length = int(response.headers['Content-Length'])
        status = response.status
        if status not in (200, 206) or (status == 200 and length != resource_files()[filename]):
            raise ValueError('资源大小或状态码与当前清单不符')
        header = f'HTTP/1.1 {status} {"Partial Content" if status == 206 else "OK"}\r\nContent-Type: application/octet-stream\r\nContent-Length: {length}\r\nConnection: close\r\n'
        if status == 206:
            header += f'Content-Range: {response.headers["Content-Range"]}\r\n'
        writer.write((header + '\r\n').encode('ascii'))
        headers_sent = True
        remaining = length
        while remaining:
            chunk = await asyncio.to_thread(response.read, min(256 * 1024, remaining))
            if not chunk:
                raise OSError('上游资源提前结束')
            writer.write(chunk)
            await writer.drain()
            remaining -= len(chunk)
        print(f'[资源下载] 已转发 {filename}，{length} 字节')
    except Exception as error:
        print(f'[资源下载失败] {filename}：{error}')
        if not headers_sent:
            writer.write(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
    finally:
        if response is not None:
            response.close()


def build_update_response() -> dict:
    """根据本机资源清单生成安装版本与资源版本，避免下发过期的固定版本。"""
    manifest_bytes = (STREAMING_ASSETS_DIR / "AssetHash_Info.bytes").read_bytes()
    manifest = json.loads(manifest_bytes)
    app_version = str(manifest["appVersion"])
    build_code = str(manifest["buildCode"])
    direct = RESOURCE_DOWNLOAD_MODE == 'direct'
    digest = hashlib.md5(manifest_bytes).hexdigest()
    assethash = f"assethash_{app_version}_{build_code}_{digest}.bytes" if direct else f"assethash_{app_version}_{build_code}.bytes"
    versions = []
    for update_type, version, version_name in (
        ("install", app_version, CLIENT_VERSION_NAME),
        ("noInstall", build_code, manifest["versionName"]),
    ):
        versions.append({
            "createDate": 1700000000000,
            "modifyDate": 1700000000000,
            "sortWeight": 0,
            "type": update_type,
            "version": version,
            "versionName": version_name,
            "matchedAppVersion": app_version,
            "forceUpdate": False,
            "fileSize": len(manifest_bytes),
            "disDate": 1700000000000,
            "downloadUrl": RESOURCE_DOWNLOAD_URL.rstrip('/') + '/' if direct and update_type == 'noInstall' else HOTFIX_BASE_URL,
            "platformType": "pc",
            "extraData": "",
            "assethash": assethash,
        })
    return {
        "code": 0,
        "errorCode": "0",
        "message": "success",
        "errorMsg": "",
        "data": versions,
    }


def read_hotfix_file(filename: str) -> bytes:
    """读取热更新文件，将版本化的资源清单请求映射到客户端现有清单。"""
    target = STREAMING_ASSETS_DIR / filename
    if target.is_file():
        return target.read_bytes()
    if re.fullmatch(r'[0-9a-f]{32}\.ys', filename):
        target = STREAMING_ASSETS_DIR / filename[0] / filename[1] / filename
        if target.is_file():
            return target.read_bytes()
    if filename.startswith("assethash_") and filename.endswith(".bytes"):
        return (STREAMING_ASSETS_DIR / "AssetHash_Info.bytes").read_bytes()
    return b""
