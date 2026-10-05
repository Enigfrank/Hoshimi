"""复制为 config_local.py 后按本机环境填写；此文件不会自动导入。"""

from pathlib import Path

GAME_CLIENT_DIR = Path(r'D:\Games\AetherGazer')
STREAMING_ASSETS_DIR = GAME_CLIENT_DIR / 'AetherGazer_Data' / 'StreamingAssets' / 'Windows'
TOLUA_PATH = GAME_CLIENT_DIR / 'AetherGazer_Data' / 'Plugins' / 'x86_64' / 'tolua.dll'
# 优先使用 AGL_CLIENT_DIR 和 HOSHIMI_RUNTIME_DIR；自定义运行目录时需同步三个路径。
# RUNTIME_DIR = Path(r'D:\HoshimiRuntime')
# LUA_SRC_DIR = RUNTIME_DIR / 'lua'
# PROTOCOL_MAP_PATH = RUNTIME_DIR / 'protocol_map.json'
HOST = '0.0.0.0'
HTTP_PROXY_PORT = 8080
TCP_GATEWAY_PORT = 5001
ENABLE_HTTPS = False
RESOURCE_DOWNLOAD_MODE = 'direct'
