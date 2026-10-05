"""读取使用者本机准备的配置；仓库不包含客户端配置导出物。"""

import json
from functools import lru_cache

from config import RUNTIME_DIR


@lru_cache(maxsize=1)
def runtime_tables() -> dict:
    """加载外部运行目录中的配置表，缺失时给出准备命令。"""
    path = RUNTIME_DIR / 'tables.json'
    if not path.is_file():
        raise FileNotFoundError(f'尚未准备本机运行依赖：{path}。请先设置 AGL_CLIENT_DIR，然后运行 python -B prepare_runtime.py。')
    return json.loads(path.read_text(encoding='utf-8'))


def load_runtime_table(name: str, tuples: bool = False):
    """恢复 JSON 中的整数键及原业务需要的元组。"""
    def restore(value):
        """递归恢复配置容器，保留非数字键。"""
        if isinstance(value, dict):
            return {int(k) if k.lstrip('-').isdigit() else k: restore(v) for k, v in value.items()}
        if isinstance(value, list):
            values = [restore(v) for v in value]
            return tuple(values) if tuples else values
        return value
    return restore(runtime_tables()[name])
