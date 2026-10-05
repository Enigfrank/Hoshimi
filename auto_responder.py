# -*- coding: utf-8 -*-
"""
Aether Gazer 自动化协议响应生成器模块
针对客户端 CS 请求协议自动匹配对应 SC 响应协议，
并依据 protocol_map.json 的元数据定义动态构建 Lua 构造与序列化脚本，
由 ToluaBridge 执行后生成符合 Protobuf 约束的二进制 Payload。
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from proto_bridge import get_bridge, ToluaBridge

logger = logging.getLogger("AutoResponder")

BASE_DIR = Path(__file__).resolve().parent
from config import PROTOCOL_MAP_PATH

DEFAULT_MAP_PATH = PROTOCOL_MAP_PATH


def _find_submsg_def(field_info: dict, current_mod: str, proto_map: dict) -> Optional[dict]:
    """根据字段元数据解析并返回对应的子消息定义字典。

    优先级：
    1. 当前模块匹配: current_mod.sub_type
    2. 包前缀匹配: package_pb.sub_type (来自 sub_full_name)
    3. 全局 sub_type
    4. 全局 sub_full_name
    """
    stype = field_info.get("sub_type")
    sfull = field_info.get("sub_full_name")

    if current_mod and stype:
        mod_key = f"{current_mod}.{stype}"
        if mod_key in proto_map:
            return proto_map[mod_key]

    if sfull and stype:
        parts = sfull.strip(".").split(".")
        if len(parts) >= 2:
            pkg_key = f"{parts[0]}_pb.{stype}"
            if pkg_key in proto_map:
                return proto_map[pkg_key]

    if stype and stype in proto_map:
        return proto_map[stype]

    if sfull and sfull in proto_map:
        return proto_map[sfull]

    return None


def _get_default_value_code(fname: str, ftype: str, now_ts_expr: str) -> str:
    """根据字段名和字段类型返回在 Lua 中的赋值表达式字符串。"""
    # 状态与结果标识默认归零
    if fname == "result" or fname.endswith("_result"):
        return "0"

    # 字符串与字节流
    if ftype in ("string", "bytes"):
        return '""'

    # 布尔值
    if ftype == "bool":
        return "false"

    # 浮点数
    if ftype in ("float", "double"):
        return "0.0"

    # 整型系列
    if ftype in ("uint32", "int32", "uint64", "int64", "sint32", "sint64",
                 "fixed32", "fixed64", "sfixed32", "sfixed64"):
        low = fname.lower()
        # 排除包含 times (次数统计) 与 state (状态枚举) 的字段
        if ("timestamp" in low or "time" in low) and ("times" not in low) and ("state" not in low):
            return now_ts_expr
        return "0"

    return "0"


class AutoResponder:
    """自动化协议响应生成器核心类。"""

    def __init__(self, map_path: Optional[Path | str] = None, bridge: Optional[ToluaBridge] = None):
        """初始化生成器，加载协议定义并构建索引结构。"""
        self.map_path = Path(map_path) if map_path else DEFAULT_MAP_PATH
        if not self.map_path.exists():
            raise FileNotFoundError(f"protocol_map.json 未找到，路径： {self.map_path}")

        logger.info(f"正在加载协议映射： {self.map_path}")
        with open(self.map_path, "r", encoding="utf-8") as f:
            self.proto_map: dict = json.load(f)

        self.bridge = bridge or get_bridge()

        # 缓存与索引初始化
        self._cs_to_sc_cache: Dict[int, Optional[int]] = {}
        self._lua_code_cache: Dict[int, str] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        """构建 SC 协议集合、模块归属索引及前缀索引以加速命令解析。"""
        self.sc_set: set[int] = set()
        self.module_to_sc: Dict[str, List[int]] = {}
        self.prefix3_to_sc: Dict[str, List[int]] = {}

        for k, v in self.proto_map.items():
            if k.startswith("sc_") and k[3:].isdigit():
                sc_id = int(k[3:])
                self.sc_set.add(sc_id)
                mod = v.get("module")
                if mod:
                    self.module_to_sc.setdefault(mod, []).append(sc_id)
                p3 = str(sc_id)[:3]
                self.prefix3_to_sc.setdefault(p3, []).append(sc_id)

        for mod in self.module_to_sc:
            self.module_to_sc[mod].sort()

        for p3 in self.prefix3_to_sc:
            self.prefix3_to_sc[p3].sort()

    def resolve_sc_cmd(self, cs_cmd: int) -> Optional[int]:
        """将客户端 CS inner cmd 映射到服务端对应的 SC cmd。

        规则：
        1. 命中缓存直接返回；
        2. 优先级 1: 检查是否存在 sc_{cs_cmd + 1}；
        3. 优先级 2: 检查是否存在同号 sc_{cs_cmd}；
        4. 优先级 3: 若 protocol_map 中存在 cs_{cs_cmd}，在对应模块下查找大于 cs_cmd 的最小 SC 或最相近 SC；
        5. 优先级 4: 按模块划分 p{cs_cmd // 1000}_pb 查找大于 cs_cmd 的最小 SC 或最相近 SC；
        6. 优先级 5: 按前 3 位数字前缀查找大于 cs_cmd 的最小 SC 或最相近 SC；
        7. 否则返回 None。
        """
        if cs_cmd in self._cs_to_sc_cache:
            return self._cs_to_sc_cache[cs_cmd]

        resolved: Optional[int] = None

        # 1. 检查 +1
        if (cs_cmd + 1) in self.sc_set:
            resolved = cs_cmd + 1
        # 2. 检查同号
        elif cs_cmd in self.sc_set:
            resolved = cs_cmd
        else:
            # 3. 检查 cs_{cs_cmd}
            cs_key = f"cs_{cs_cmd}"
            if cs_key in self.proto_map:
                mod = self.proto_map[cs_key].get("module")
                if mod and mod in self.module_to_sc:
                    candidates = self.module_to_sc[mod]
                    gt = [c for c in candidates if c > cs_cmd]
                    resolved = min(gt, key=lambda c: c - cs_cmd) if gt else min(candidates, key=lambda c: abs(c - cs_cmd))

            # 4. 按模块编号回退 (如 15000 -> p15_pb)
            if resolved is None:
                mod_name = f"p{cs_cmd // 1000}_pb"
                if mod_name in self.module_to_sc:
                    candidates = self.module_to_sc[mod_name]
                    gt = [c for c in candidates if c > cs_cmd]
                    resolved = min(gt, key=lambda c: c - cs_cmd) if gt else min(candidates, key=lambda c: abs(c - cs_cmd))

            # 5. 按前缀回退
            if resolved is None:
                p3 = str(cs_cmd)[:3]
                if p3 in self.prefix3_to_sc:
                    candidates = self.prefix3_to_sc[p3]
                    gt = [c for c in candidates if c > cs_cmd]
                    resolved = min(gt, key=lambda c: c - cs_cmd) if gt else min(candidates, key=lambda c: abs(c - cs_cmd))

        self._cs_to_sc_cache[cs_cmd] = resolved
        return resolved

    def build_lua_script(self, sc_cmd: int, fixed_timestamp: Optional[int] = None) -> str:
        """针对指定 SC 命令动态生成递归填充 required 字段并序列化的 Lua 脚本代码。"""
        # 如果未指定特定时间戳且已存在缓存，直接复用缓存代码
        if fixed_timestamp is None and sc_cmd in self._lua_code_cache:
            return self._lua_code_cache[sc_cmd]

        sc_name = f"sc_{sc_cmd}"
        if sc_name not in self.proto_map:
            raise KeyError(f"协议 {sc_name} 未在协议映射中找到")

        info = self.proto_map[sc_name]
        mod = info.get("module")
        if not mod:
            raise ValueError(f"未找到对应模块： {sc_name}")

        now_ts_expr = str(fixed_timestamp) if fixed_timestamp is not None else "now_ts"

        lines = [
            "local now_ts = os.time()",
            f'local m = require("{mod}").{sc_name}()'
        ]

        def fill_fields(path: str, fields: list, current_mod: str, visited: set) -> None:
            """递归遍历字段并生成对应填充语句。"""
            for f in fields:
                fname = f.get("name")
                ftype = f.get("type")
                flabel = f.get("label")
                subpath = f"{path}.{fname}"

                # 必填字段处理
                if flabel == "required":
                    if ftype == "message":
                        lines.append(f"{subpath}:SetInParent()")
                        sub_def = _find_submsg_def(f, current_mod, self.proto_map)
                        if sub_def:
                            sub_mod = sub_def.get("module", current_mod)
                            sub_key = (sub_def.get("name"), sub_mod)
                            if sub_key not in visited:
                                fill_fields(subpath, sub_def.get("fields", []), sub_mod, visited | {sub_key})
                    else:
                        val = _get_default_value_code(fname, ftype, now_ts_expr)
                        lines.append(f"{subpath} = {val}")

                # optional 的 result 字段默认设为 0
                elif fname == "result" and flabel == "optional" and ftype in ("uint32", "int32", "uint64", "int64"):
                    lines.append(f"{subpath} = 0")

        fill_fields("m", info.get("fields", []), mod, set())
        lines.append("return m:SerializeToString()")

        code = "(function()\n  " + "\n  ".join(lines) + "\nend)()"

        if fixed_timestamp is None:
            self._lua_code_cache[sc_cmd] = code

        return code

    def generate_response(self, cmd: int, fixed_timestamp: Optional[int] = None, result: int = 0) -> Optional[Tuple[int, bytes]]:
        """为指定的客户端 inner cmd 生成对应的服务端响应 (resp_cmd, resp_payload_bytes)。

        若无对应 SC 协议或生成过程中出现异常，进行捕获并返回 None。
        """
        try:
            sc_cmd = self.resolve_sc_cmd(cmd)
            if sc_cmd is None:
                logger.warning(f"CS 指令没有对应的 SC 映射，指令={cmd}")
                return None

            lua_code = self.build_lua_script(sc_cmd, fixed_timestamp=fixed_timestamp)
            result_field = next((field for field in self.proto_map[f'sc_{sc_cmd}']['fields']
                                 if field['name'] == 'result'), None)
            if result and result_field and result_field['type'] in ('uint32', 'int32', 'uint64', 'int64'):
                # 保留必填结构，但未实现的请求必须明确返回失败。
                lua_code = lua_code.replace('return m:SerializeToString()',
                    f"m.result = {int(result)}\nreturn m:SerializeToString()")
            payload = self.bridge.run_lua_expr(lua_code)
            return (sc_cmd, payload)

        except Exception as e:
            logger.error(f"生成响应失败，指令={cmd}: {e}", exc_info=True)
            return None


# 单例实例
_DEFAULT_RESPONDER: Optional[AutoResponder] = None


def get_responder() -> AutoResponder:
    """获取 AutoResponder 的单例实例。"""
    global _DEFAULT_RESPONDER
    if _DEFAULT_RESPONDER is None:
        _DEFAULT_RESPONDER = AutoResponder()
    return _DEFAULT_RESPONDER


def generate_response(cmd: int, result: int = 0) -> Optional[Tuple[int, bytes]]:
    """公共接口：针对给定的客户端 inner cmd，返回 (resp_cmd, resp_payload_bytes) 或 None。"""
    return get_responder().generate_response(cmd, result=result)
