# -*- coding: utf-8 -*-
"""
AGL_Server 全局配置文件
支持通过环境变量、config_local.py 或直接修改本文件覆盖默认配置。
"""

import os
import sys
import hashlib
import json
from pathlib import Path

# 服务端项目根目录
BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------
# 1. 游戏客户端路径配置
# ---------------------------------------------------------
# 默认指向客户端根目录（包含 AetherGazer.exe 及 AetherGazer_Data 的目录）
# 可通过系统环境变量 AGL_CLIENT_DIR 进行覆盖，亦可在 config_local.py 中指定
DEFAULT_CLIENT_DIR = r"D:\Games\AetherGazer"
GAME_CLIENT_DIR = Path(os.getenv("AGL_CLIENT_DIR", DEFAULT_CLIENT_DIR))

# 自动推导路径
STREAMING_ASSETS_DIR = Path(
    os.getenv(
        "AGL_STREAMING_ASSETS_DIR",
        str(GAME_CLIENT_DIR / "AetherGazer_Data" / "StreamingAssets" / "Windows")
    )
)

TOLUA_PATH = Path(
    os.getenv(
        "AGL_TOLUA_PATH",
        str(GAME_CLIENT_DIR / "AetherGazer_Data" / "Plugins" / "x86_64" / "tolua.dll")
    )
)

# ---------------------------------------------------------
# 2. 项目资源路径配置
# ---------------------------------------------------------
# 客户端解包的 Lua 目录
RUNTIME_DIR = Path(os.getenv("HOSHIMI_RUNTIME_DIR", str(Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Hoshimi" / "runtime")))
LUA_SRC_DIR = RUNTIME_DIR / "lua"
PROTOCOL_MAP_PATH = RUNTIME_DIR / "protocol_map.json"

# HTTPS 证书路径
CERT_FILE = BASE_DIR / "cert.pem"
KEY_FILE = BASE_DIR / "key.pem"

# ---------------------------------------------------------
# 3. 网络监听与端口配置
# ---------------------------------------------------------
HOST = os.getenv("AGL_HOST", "0.0.0.0")
HTTP_PROXY_PORT = int(os.getenv("AGL_HTTP_PORT", "8080"))
HTTPS_DIRECT_PORT = int(os.getenv("AGL_HTTPS_PORT", "443"))
# 新客户端切换脚本将 SDK 地址改为本地 HTTP；旧证书模式可显式启用。
ENABLE_HTTPS = os.getenv("AGL_ENABLE_HTTPS", "0") == "1"
TCP_GATEWAY_PORT = int(os.getenv("AGL_TCP_PORT", "5001"))

# ---------------------------------------------------------
# 4. 客户端版本与热更新配置
# ---------------------------------------------------------
CLIENT_VERSION = os.getenv("AGL_CLIENT_VERSION", "307")
CLIENT_VERSION_NAME = os.getenv("AGL_CLIENT_VERSION_NAME", "v5.2.0")
HOTFIX_BASE_URL = os.getenv("AGL_HOTFIX_URL", f"http://127.0.0.1:{HTTP_PROXY_PORT}/hotfix/")
RESOURCE_DOWNLOAD_URL = os.getenv("AGL_RESOURCE_DOWNLOAD_URL", "https://download-eo.ys4fun.com/pc/resources/")
# direct：客户端使用官方 CDN；proxy：由本地服务转发缺失资源。
RESOURCE_DOWNLOAD_MODE = os.getenv("AGL_RESOURCE_MODE", "direct")

# ---------------------------------------------------------
# 5. 本地私有配置覆盖
# 若根目录下存在 config_local.py（已被 .gitignore 忽略），将自动导入覆盖上述配置
# ---------------------------------------------------------
try:
    import config_local  # type: ignore

    for _k, _v in vars(config_local).items():
        if not _k.startswith("__"):
            globals()[_k] = _v
except ImportError:
    pass


def validate_environment() -> tuple[bool, list[str]]:
    """验证当前运行环境及必要依赖，返回 (是否通过, 错误/警告信息列表)。"""
    issues = []
    if RESOURCE_DOWNLOAD_MODE not in ('direct', 'proxy'):
        issues.append('[错误] AGL_RESOURCE_MODE 必须为 direct 或 proxy。')

    # 1. Python 架构检测
    is_64bit = sys.maxsize > 2**32
    if not is_64bit:
        issues.append(
            "[错误] 当前 Python 为 32 位版本！tolua.dll 为 64 位动态库，"
            "必须使用 64 位 Python 3.10+ 运行本服务。"
        )

    # 2. tolua.dll 检测
    if not TOLUA_PATH.is_file():
        issues.append(
            f"[错误] 未找到 tolua.dll 动态链接库！\n"
            f"       当前路径: {TOLUA_PATH}\n"
            f"       解决方式: 请在 config.py 或 config_local.py 中修改 GAME_CLIENT_DIR，"
            f"或设置环境变量 AGL_CLIENT_DIR 指向游戏安装目录。"
        )

    # 3. Lua 源码目录检测
    if not LUA_SRC_DIR.is_dir():
        issues.append(
            f"[错误] 未找到 Lua 脚本目录: {LUA_SRC_DIR}\n"
            f"       解决方式: 请先运行 python -B prepare_runtime.py 准备本机依赖。"
        )

    # 导出配置必须与使用中的本机客户端清单一致。
    try:
        metadata = json.loads((RUNTIME_DIR / 'runtime.json').read_text(encoding='utf-8'))
        digest = hashlib.sha256((STREAMING_ASSETS_DIR / 'AssetHash_Info.bytes').read_bytes()).hexdigest()
        if metadata.get('schema_version') != 1 or metadata.get('manifest_sha256') != digest:
            issues.append('[错误] 本机依赖与客户端版本不一致，请重新运行 python -B prepare_runtime.py。')
        if not PROTOCOL_MAP_PATH.is_file() or not (RUNTIME_DIR / 'tables.json').is_file():
            issues.append('[错误] 本机运行依赖不完整，请重新运行 python -B prepare_runtime.py。')
    except (OSError, ValueError):
        issues.append('[错误] 缺少运行元数据或客户端资源清单，请检查 AGL_CLIENT_DIR 并运行 python -B prepare_runtime.py。')

    # 4. HTTPS 证书检测
    if ENABLE_HTTPS and (not CERT_FILE.is_file() or not KEY_FILE.is_file()):
        issues.append(
            f"[警告] 未检测到 HTTPS 证书文件 (cert.pem / key.pem)！\n"
            f"          解决方式: 请在终端中运行以下命令生成自签证书:\n"
            f"          pwsh -File 自行提供 CERT_FILE 和 KEY_FILE；默认接入无需证书。"
        )

    has_errors = any(msg.startswith("[错误]") for msg in issues)
    return (not has_errors, issues)
