import asyncio
import json
import os
from pathlib import Path
import ssl
import struct
import sys
import time
import zlib

from config import (
    BASE_DIR,
    CERT_FILE,
    KEY_FILE,
    HOST,
    HTTP_PROXY_PORT,
    HTTPS_DIRECT_PORT,
    ENABLE_HTTPS,
    TCP_GATEWAY_PORT,
    validate_environment,
)
from hotfix import build_update_response, read_hotfix_file, remote_resource_url, stream_remote_resource
from cdn_connection import is_resource_cdn, tunnel_resource_cdn
from proto_bridge import get_bridge
from auto_responder import generate_response
from push_data import SHOP_GOODS_NOREFRESH
from currency_data import build_currency_balances, materialize_currencies
from sign_progress import SIGN_COMMANDS, sign_request, sign_pushes, initialize_sign
from account_unlocks import unlock_developer, illustrated_data, scene_view_data
from communications import MAIL_COMMANDS, mail_request, mail_brief, mail_list, announcement_data
from chapter_maps import CHAPTER_MAP_COMMANDS, chapter_map_request, chapter_map_pushes
from hero_data import build_max_heroes
from supply_data import build_supply_goods
from gameplay_data import build_gameplay_pushes, passport_data, equip_battle_data, battle_progress_pushes
from gameplay_protocol import encode_message, decode_message
from battle_data import start_battle, settle_battle, start_story
from challenge_data import boss_data, enchantment_data, challenge_pushes
from battle_udp import BattleUDP
from reserve_data import save_reserve, save_battle_team
from profile_data import profile_data, profile_request, PROFILE_COMMANDS
from hero_preferences import hero_info_data, hero_request, HERO_COMMANDS
from task_progress import refresh_task_periods, update_task_progress, claim_tasks, claim_task_points
from gameplay_data import task_data, task_points
from shop_transactions import buy_goods, shop_stock, refresh_shop_periods
from loadout_storage import LOADOUT_COMMANDS, loadout_request, servant_data, chip_data
from passport_progress import passport_request
from challenge_requests import CHALLENGE_COMMANDS, challenge_request
from equip_cultivation import EQUIP_COMMANDS, equip_request
from servant_cultivation import SERVANT_COMMANDS, servant_request
from polyhedron_game import POLYHEDRON_COMMANDS, polyhedron_data, polyhedron_request
from battle_rewards import inventory_pushes, equipment_data
from native_protocol import battle_report
from equip_exploration import exploration_request
from battle_progress import story_progress
from daily_progress import DAILY_COMMANDS, daily_request, daily_pushes
from inventory_usage import use_items
from chapter_rewards import chapter_reward_data, claim_chapter_reward, read_chapter_archive
from native_protocol import fields as native_fields, integer as native_int, message as native_message
from user_storage import get_user_manager, DEFAULT_STICKERS
from account_auth import sdk_authenticate, matches_game_account
from gacha_progress import DRAW_COMMANDS, draw_request, draw_init, bonus_pushes
from skin_draw_progress import SKIN_DRAW_COMMANDS, skin_request, skin_pushes
from typing import Optional, Set, Dict, Any

SERVER_LIST_RESPONSE = {
    "code": 0,
    "errorCode": "0",
    "message": "success",
    "errorMsg": "",
    "data": [
        {
            "serverId": "1",
            "serverName": "本地单机服",
            "env": "prod",
            "ip": "127.0.0.1",
            "port": TCP_GATEWAY_PORT,
            "newServerFlag": 1,
            "maintain": False,
            "maintainReason": "",
            "config": [
                {"key": "STOP_HOT_FIX", "value": "1"}
            ],
            "gameUserInfoList": []
        }
    ]
}

GATEWAY_RESPONSE = {
    "code": 0,
    "errorCode": "0",
    "message": "success",
    "errorMsg": "",
    "data": {
        "serverId": "1",
        "serverName": "LocalServer",
        "env": "prod",
        "ip": "127.0.0.1",
        "port": TCP_GATEWAY_PORT,
        "newServerFlag": 0,
        "maintain": False,
        "maintainReason": "",
        "config": [
            {"key": "STOP_HOT_FIX", "value": "1"}
        ],
        "gameUserInfoList": []
    }
}

GAMECFG_RESPONSE = {
    "code": 0,
    "errorCode": "0",
    "message": "success",
    "errorMsg": "",
    "data": {
        "helpUrl": "",
        "privacyUrl": "",
        "userAgreementUrl": "",
        "childrenPrivacyUrl": "",
        "thirdSdkPrivacyUrl": "",
        "infoCollectionListUrl": "",
        "regist": None
    }
}

NOTICE_RESPONSE = {
    "code": 0,
    "errorCode": "0",
    "message": "success",
    "errorMsg": "",
    "data": None
}

AGREEMENT_RESPONSE = {
    "code": 0,
    "errorCode": "0",
    "message": "success",
    "errorMsg": "",
    "data": None
}

# --- ETFramework Protocol Definition (Little-Endian) ---
def pack_packet(opcode: int, body: bytes = b"", flag: int = 0, rpc_id: int = 0) -> bytes:
    if flag in (1, 2):
        packet_size = 7 + len(body)
        return struct.pack("<HBHI", packet_size, flag, opcode, rpc_id) + body
    else:
        packet_size = 3 + len(body)
        return struct.pack("<HBH", packet_size, flag, opcode) + body

def unpack_packet_payload(payload: bytes):
    if len(payload) < 3:
        raise ValueError(f"数据包载荷过短: {len(payload)}")
    flag, opcode = struct.unpack("<BH", payload[:3])
    if flag in (1, 2):
        if len(payload) < 7:
            raise ValueError(f"RPC 载荷过短: {len(payload)}")
        rpc_id = struct.unpack("<I", payload[3:7])[0]
        body = payload[7:]
    else:
        rpc_id = 0
        body = payload[3:]
    return flag, opcode, rpc_id, body

# --- YSTcpConnection Protocol Definition (Big-Endian) ---
def pack_ystcp(cmd: int, body: bytes = b"", is_compress: int = 0, index: int = 0, server_index: int = 0) -> bytes:
    """编码响应帧；大型初始化包使用客户端支持的 zlib 压缩。"""
    if is_compress or len(body) + 9 > 65535:
        body = zlib.compress(body)
        is_compress = 1
    raw_size = len(body) + 9
    if raw_size > 65535:
        raise ValueError(f"响应 {cmd} 压缩后仍超过 uint16 帧长度上限")
    return struct.pack(">HBIHH", raw_size, is_compress, cmd, index, server_index) + body

def unpack_ystcp(payload: bytes):
    if len(payload) < 9:
        raise ValueError(f"YSTcp 载荷过短: {len(payload)}")
    is_compress, cmd, index, server_index = struct.unpack(">BIHH", payload[:9])
    body = payload[9:]
    if is_compress:
        body = zlib.decompress(body)
    return is_compress, cmd, index, server_index, body

def handle_ystcp_message(cmd: int, index: int, server_index: int, body: bytes) -> bytes | None:
    bridge = get_bridge()
    resp_cmd = None
    resp_pb = None
    if cmd == 10038:
        resp_cmd = 10039
        resp_pb = bridge.encode_sc_10039(server_id=1, ip="127.0.0.1", port=TCP_GATEWAY_PORT)
    elif cmd == 10042:
        resp_cmd = 10043
        resp_pb = bridge.encode_sc_10043()
    elif cmd == 10200:
        resp_cmd = 10201
        resp_pb = bridge.encode_sc_10201()
    elif cmd == 10050:
        resp_cmd = 10051
        resp_pb = bridge.encode_sc_10051()
    elif cmd == 10500:
        resp_cmd = 10501
        resp_pb = bridge.encode_sc_10501()
    elif cmd == 54030:
        resp_cmd = 54031
        resp_pb = bridge.encode_sc_54031()
    elif cmd == 32108:
        resp_cmd = 32109
        resp_pb = bridge.encode_sc_32109(result=0)
    else:
        mapped = generate_response(cmd)
        if mapped:
            resp_cmd, resp_pb = mapped
            print(f"[YSTcp 自动响应] 已自动响应指令 {cmd} -> sc_{resp_cmd} ({len(resp_pb)} 字节)")
    
    if resp_cmd is not None and resp_pb is not None:
        return pack_ystcp(resp_cmd, resp_pb, index=0, server_index=index)
    return None

# --- Minimal Protobuf Varint Helper ---
def encode_varint(value: int) -> bytes:
    bits = value & 0xFFFFFFFFFFFFFFFF
    buf = bytearray()
    while True:
        b = bits & 0x7F
        bits >>= 7
        if bits:
            buf.append(b | 0x80)
        else:
            buf.append(b)
            break
    return bytes(buf)

def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    res = 0
    shift = 0
    idx = offset
    while idx < len(data):
        b = data[idx]
        idx += 1
        res |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return res, idx

def decode_ping(body: bytes) -> int:
    client_time = 0
    idx = 0
    while idx < len(body):
        tag_byte, idx = decode_varint(body, idx)
        wire_type = tag_byte & 0x07
        field_num = tag_byte >> 3
        if wire_type == 0:
            val, idx = decode_varint(body, idx)
            if field_num == 1:
                client_time = val
        elif wire_type == 2:
            length, idx = decode_varint(body, idx)
            idx += length
        else:
            break
    return client_time

def encode_pong(client_time: int, server_time: int) -> bytes:
    return b"\x08" + encode_varint(client_time) + b"\x10" + encode_varint(server_time)


class ClientSession:
    def __init__(self, writer: asyncio.StreamWriter, peer: Any):
        self.writer = writer
        self.peer = peer
        self.user_id: int = 0
        self.account: str = ""
        self.token: str = ""
        self.user_data: Dict[str, Any] = {}
        self.delayed_tasks: Set[asyncio.Task] = set()
        self.closed: bool = False
        self.battle: dict | None = None

    def add_delayed_task(self, task: asyncio.Task):
        if self.closed:
            task.cancel()
            return
        self.delayed_tasks.add(task)
        task.add_done_callback(self.delayed_tasks.discard)

    def close(self):
        self.closed = True
        for task in list(self.delayed_tasks):
            if not task.done():
                task.cancel()
        self.delayed_tasks.clear()
        try:
            if not self.writer.is_closing():
                self.writer.close()
        except Exception:
            pass

CLIENT_SESSIONS: Dict[asyncio.StreamWriter, ClientSession] = {}


def account_pushes(user):
    """GM 与邮件共用账号同步，库存、角色、资料和图鉴一次刷新。"""
    return inventory_pushes(user) + [(12009, decode_message(12009,
        get_bridge().encode_sc_12009(user_level=user.get('level', 80)), 'sc')),
        (14009, hero_info_data(user)), (46011, servant_data(user)),
        (32009, profile_data(user)), (32011, scene_view_data(user)), (52001, illustrated_data(user)),
        (30001, mail_brief(user))]


def sync_online_account(uid):
    """从最新存档同步相同 UID 的全部在线会话。"""
    user = get_user_manager().get_user_by_uid(uid)
    if not user:
        return
    sessions = [s for s in CLIENT_SESSIONS.values() if s.user_id == uid and not s.writer.is_closing()]
    if not sessions:
        return
    frames = b''.join(pack_ystcp(c, encode_message(c, v)) for c, v in account_pushes(user))
    for session in sessions:
        session.user_data = user
        session.writer.write(frames)


def sync_announcements():
    """向当前在线客户端广播已生效公告。"""
    frame = pack_ystcp(30099, encode_message(30099, announcement_data(get_user_manager())))
    for session in list(CLIENT_SESSIONS.values()):
        if session.user_id and not session.writer.is_closing():
            session.writer.write(frame)


async def publish_scheduled_announcements():
    """公告排期开始或结束时更新在线客户端，无需重新登录。"""
    previous = None
    while True:
        current = announcement_data(get_user_manager())
        if current != previous:
            sync_announcements()
            previous = current
        await asyncio.sleep(10)


def handle_native_battle(packet: bytes, context: dict) -> list[bytes]:
    """处理单人战斗握手与实际结果上报，不生成联机同步帧。"""
    flag, opcode, rpc_id, payload = unpack_packet_payload(packet)
    if opcode == 123:  # 单人输入在客户端模拟；这里是原始帧数据，不是 protobuf。
        return []
    if opcode != 100:
        print(f'[战斗原生消息] 操作码={opcode} 字节数={len(payload)}')
    response_flag = 2 if flag == 1 else 0

    def reply(command, body):
        """KCP 消息直接带 Packet 头，不附 TCP 长度。"""
        return pack_packet(command, body, flag=response_flag, rpc_id=rpc_id)[2:]

    if opcode == 100:
        if len(payload) != 8:
            raise ValueError('战斗时间同步长度错误')
        return [reply(101, payload + struct.pack('<q', int(time.time()*1000)))]
    values = native_fields(payload)
    id_field = 2 if opcode == 130 else 1
    battle_id = values.get(id_field, [context.get('battle_id', 0)])[0]
    current = next((s for s in CLIENT_SESSIONS.values() if s.battle and s.battle['id'] == battle_id), None)
    if current is None:
        raise ValueError('战斗会话不存在')
    context['battle_id'] = battle_id
    uid = current.user_id
    if opcode == 126:
        return [reply(127, native_int(1, battle_id) + native_int(2, 1) + native_int(3, values.get(3, [0])[0]))]
    if opcode == 128:
        member = native_int(1, uid) + native_int(2, 1)
        return [reply(129, native_message(1, native_int(1, uid) + native_message(2, member)))]
    if opcode == 130:
        if values.get(1, [0])[0] != uid:
            raise ValueError('战斗 UID 不匹配')
        # RoomKey=0 是客户端单人模拟分支；非零值会按联机席位重建实体。
        start = native_int(1, 0)
        return [reply(131, native_int(1, uid)), pack_packet(125, start)[2:]]
    if opcode == 132:
        if values.get(2, [0])[0] != uid or values.get(3, [0])[0] not in (1, 2, 3, 4):
            raise ValueError('无效战斗结果')
        user = get_user_manager().get_user_by_uid(uid)
        saved = user.get('battle_session')
        if saved and saved['id'] == battle_id:
            current.battle = saved
        if current.battle['reported'] is None:
            current.battle['reported'] = {'result': values[3][0], 'info': battle_report(values.get(4, [b''])[0])}
            user['battle_session'] = current.battle
            get_user_manager().save_user(user)
        print(f"[战斗上报] ID={battle_id} 结果={values[3][0]}")
        return [reply(134, native_int(1, 0)), pack_packet(135, native_int(1, 0))[2:]]
    return []

def handle_tcp_message(opcode: int, flag: int, rpc_id: int, body: bytes, writer=None, session: Optional[ClientSession] = None) -> bytes | None:
    """处理 ET 请求与内嵌游戏协议，构造登录响应及有序数据推送。"""
    if opcode == 100:  # Op_ping -> Op_pong
        c_time = decode_ping(body)
        s_time = int(time.time() * 1000)
        resp_flag = 2 if flag == 1 else 0
        resp_body = encode_pong(c_time, s_time)
        return pack_packet(101, resp_body, flag=resp_flag, rpc_id=rpc_id)
    elif opcode == 102:  # Op_B2G_ConnectRequest -> Op_G2B_ConnectResponse
        resp_flag = 2 if flag == 1 else 0
        resp_body = b"\x08\x00\x10\x01\x18\x01"
        return pack_packet(103, resp_body, flag=resp_flag, rpc_id=rpc_id)
    elif opcode == 2048:  # Lua CS/SC Protocol Frame
        if len(body) < 8:
            print(f"[TCP 错误] 操作码 2048 的消息体过短: {len(body)}")
            return None
        cmd, c_idx, s_idx = struct.unpack("<IHH", body[:8])
        pb_payload = body[8:]
        print(f"[TCP 接收 2048] 指令={cmd} (0x{cmd:04X}) 客户端索引={c_idx} 服务端索引={s_idx} 载荷长度={len(pb_payload)}")
        
        bridge = get_bridge()
        resp_cmd = None
        resp_pb = None
        resp_extra = None
        resp_before = []
        if session and not session.user_id and cmd not in (10038, 10042):
            # 游戏业务必须在账号验证完成后才能读取或修改存档。
            session.close()
            return None
        if session and session.user_data:
            # GM、聊天和其他连接也会修改存档；每次请求读取最新版本。
            saved_user = get_user_manager().get_user_by_uid(session.user_id)
            if cmd not in (10038, 10042) and (not saved_user or not session.token or saved_user.get('token') != session.token):
                session.close()
                return None
            session.user_data = saved_user or session.user_data
            if session.user_data.get('battle_session'):
                session.battle = session.user_data['battle_session']
            refresh_task_periods(session.user_data)
            refresh_shop_periods(session.user_data)
        if cmd == 10038:  # cs_10038 -> sc_10039
            user_mgr = get_user_manager()
            login = decode_message(10038, pb_payload, 'cs')
            user = user_mgr.authenticate_token(login.get('token', ''))
            if not user or not matches_game_account(user, login.get('account')):
                return pack_ystcp(10039, encode_message(10039, {'result': 1}), index=c_idx, server_index=c_idx)
            if session:
                session.user_id = user["uid"]
                session.account = user["account"]
                session.token = user["token"]
                session.user_data = user
            resp_cmd = 10039
            resp_pb = bridge.encode_sc_10039(server_id=1, ip="127.0.0.1", port=TCP_GATEWAY_PORT, user_id=user["uid"], gstoken=user["token"], is_new_player=0)
            print(f"[服务端] 已生成 sc_10039，UID={user['uid']} ({len(resp_pb)} 字节)")
        elif cmd == 10042:  # cs_10042 -> sc_10043 (+ push game data)
            user_mgr = get_user_manager()
            login = decode_message(10042, pb_payload, 'cs')
            user = user_mgr.authenticate_token(login.get('gstoken', ''))
            if not user or login.get('user_id') != user['uid'] or not matches_game_account(user, login.get('account')):
                return pack_ystcp(10043, bridge.encode_sc_10043(result=1), index=c_idx, server_index=c_idx)
            if user['account'].casefold() == 'developer':
                user["heroes"] = build_max_heroes(user.get("heroes"))
            materialize_currencies(user)
            unlock_developer(user)
            initialize_sign(user)
            refresh_task_periods(user)
            refresh_shop_periods(user)
            update_task_progress(user, 1)
            if session:
                session.user_id = user["uid"]
                session.account = user["account"]
                session.token = user["token"]
                session.user_data = user
                session.battle = user.get('battle_session')
            balances = build_currency_balances(user)
            heroes = user["heroes"]
            supplies = build_supply_goods()
            shop_goods = dict(SHOP_GOODS_NOREFRESH)
            for sid, goods in supplies.items():
                shop_goods[sid] = shop_goods.get(sid, []) + [item["goods_id"] for item in goods]
            resp_cmd = 10043
            resp_pb = bridge.encode_sc_10043(result=0, register_timestamp=user.get('created_at', int(time.time())), uid_sign=f"mock_uid_sign_{user['uid']}")
            stickers = user.get("custom_stickers", DEFAULT_STICKERS)
            resp_extra = [
                (23009, encode_message(23009, {'nick': user.get('nick', 'Developer'),
                    'total_exp': user.get('total_exp', 70000), 'hero_num': len(heroes),
                    'plot_progress': user.get('plot_progress', 0 if user.get('account_template') == 'normal' else 1), 'is_changed_nick': user.get('is_changed_nick', 0),
                    'system_change_nick_times': user.get('system_change_nick_times', 0)}), 0, 0.0),
                (12009, bridge.encode_sc_12009(user_level=user.get("level", 80)), 0, 0.0),
                (14009, encode_message(14009, hero_info_data(user)), 0, 0.0),
                (15009, bridge.encode_sc_15009(balances), 0, 0.0),
                (13009, encode_message(13009, equipment_data(user)), 0, 0.0),
                (13057, encode_message(13057, {'type_list': user.get('equip_auto_decompose', [])}), 0, 0.0),
                (17009, encode_message(17009, inventory_pushes(user)[1][1]), 0, 0.0),
                (46011, encode_message(46011, servant_data(user)), 0, 0.0),
                (50001, encode_message(50001, chip_data(user)), 0, 0.0),
                (16015, encode_message(16015, draw_init(user)), 0, 0.0),
                *[(c, encode_message(c, v), 0, 0.0) for c, v in bonus_pushes(user)],
                *[(c, encode_message(c, v), 0, 0.0) for c, v in skin_pushes(user)],
                (19029, bridge.encode_sc_19029(), 0, 0.0),
                (12039, bridge.encode_sc_12039(stickers), 0, 0.0),
                (19001, bridge.encode_sc_19001(), 0, 0.0),
                (30001, encode_message(30001, mail_brief(user)), 0, 0.0),
                (30099, encode_message(30099, announcement_data(user_mgr)), 0, 0.0),
                (52001, encode_message(52001, illustrated_data(user)), 0, 0.0),
                *[(c, encode_message(c, v), 0, 0.0) for c, v in sign_pushes(user) + chapter_map_pushes(user)],
                (11001, bridge.encode_sc_11001(), 0, 0.0),
                (12011, bridge.encode_sc_12011(user.get('finished_guides')), 0, 0.0),
                (12111, bridge.encode_sc_12111(user.get('finished_weak_guides')), 0, 0.0),
                (28837, bridge.encode_sc_28837(), 0, 0.0),
                (32009, encode_message(32009, profile_data(user)), 0, 0.0),
                (32011, encode_message(32011, scene_view_data(user)), 0, 0.0),
                (32051, encode_message(32051, {'list': [
                    {'skin_id': i, 'gift_acquire': True} for i in user.get('skin_gifts', [])]}), 0, 0.0),
                (12001, encode_message(12001, {'story_list': user.get('read_stories', [])}), 0, 0.0),
                (12033, encode_message(12033, user.get('birthday', {'month': 0, 'day': 0})), 0, 0.0),
                (10600, bridge.encode_sc_10600(), 0, 0.0),
                (24009, encode_message(24009, story_progress(user)), 0, 0.0),
                (24017, encode_message(24017, chapter_reward_data(user)), 0, 0.0),
                (24043, encode_message(24043, {'plot_list': user.get('chapter_archives', [])}), 0, 0.0),
                *build_gameplay_pushes(user),
                *[(20003, bridge.encode_sc_20003(sid, goods), 0, 0.0) for sid, goods in supplies.items()],
                (20009, encode_message(20009, shop_stock(user)), 0, 0.0),
                (10501, bridge.encode_sc_10501(), 0, 0.0),
                (10201, bridge.encode_sc_10201(), 0, 0.0),
            ]
            user_mgr.save_user(user)
            print(f"[服务端] 已生成 sc_10043，UID={user['uid']} + 数据推送")
        elif cmd in DRAW_COMMANDS or cmd in SKIN_DRAW_COMMANDS:
            from copy import deepcopy
            resp_cmd = cmd + 1
            try:
                if not session or not session.user_data:
                    raise ValueError('未登录')
                user = deepcopy(session.user_data)
                handler = draw_request if cmd in DRAW_COMMANDS else skin_request
                values = handler(user, cmd, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                pushes = []
                if cmd in (16010, 16022, 68152, 68156, 68186):
                    pushes = inventory_pushes(user) + [(14009, hero_info_data(user)),
                        (46011, servant_data(user)), (52001, illustrated_data(user)),
                        (32009, profile_data(user))] + bonus_pushes(user)
                if cmd in (68152, 68186):
                    pushes += skin_pushes(user, {decode_message(cmd, pb_payload)['pool_id']})
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
                get_user_manager().save_user(user)
                session.user_data = user
            except ValueError as error:
                print(f'[探测拒绝] 指令={cmd} {error}')
                resp_extra = None
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in SIGN_COMMANDS or cmd in MAIL_COMMANDS or cmd in CHAPTER_MAP_COMMANDS:
            from copy import deepcopy
            resp_cmd = cmd + 1
            try:
                if not session or not session.user_data:
                    raise ValueError('未登录')
                user = deepcopy(session.user_data)
                handler = sign_request if cmd in SIGN_COMMANDS else mail_request if cmd in MAIL_COMMANDS else chapter_map_request
                values = handler(user, cmd, decode_message(cmd, pb_payload))
                if cmd == 56002:
                    # 客户端使用 Push 单向上报红点；56003 成功响应会弹出兑换码提示。
                    get_user_manager().save_user(user)
                    session.user_data = user
                    return None
                resp_pb = encode_message(resp_cmd, values)
                pushes = []
                if cmd in SIGN_COMMANDS:
                    # 11011 回调会自行更新签到；重发角色与签到初始化会打断领奖页面。
                    pushes = inventory_pushes(user)
                    if cmd in (17028, 17030):
                        pushes += [(c, v) for c, v in sign_pushes(user) if c == 17027]
                elif cmd in MAIL_COMMANDS:
                    # 邮件回调自行更新缓存；30001 会重新查询列表并丢失已加载的正文。
                    if cmd == 30004:
                        pushes = inventory_pushes(user)
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
                if cmd not in MAIL_COMMANDS or user != session.user_data:
                    get_user_manager().save_user(user)
                session.user_data = user
            except ValueError as error:
                print(f'[操作拒绝] 指令={cmd} {error}')
                if cmd == 56002:
                    return None
                resp_extra = None
                resp_pb = encode_message(resp_cmd, {'result': 1}) if cmd not in (30002, 30006, 30020) else encode_message(resp_cmd, {})
        elif cmd in (38014, 38016, 54300):  # 单向上传，没有对应的 SC 协议。
            return None
        elif cmd == 20012:
            resp_cmd = 20013
            try:
                if not session:
                    raise ValueError('未登录')
                values = buy_goods(session.user_data, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
                pushes = inventory_pushes(session.user_data) + [(20009, shop_stock(session.user_data)),
                    (14009, hero_info_data(session.user_data)), (46011, servant_data(session.user_data)),
                    (32009, profile_data(session.user_data))]
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
            except ValueError as error:
                print(f'[商店拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in (24014, 24040):
            resp_cmd = cmd + 1
            try:
                if not session or not session.user_data:
                    raise ValueError('未登录')
                handler = claim_chapter_reward if cmd == 24014 else read_chapter_archive
                values = handler(session.user_data, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                pushes = inventory_pushes(session.user_data) + [(24017, chapter_reward_data(session.user_data))]
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
                get_user_manager().save_user(session.user_data)
            except ValueError as error:
                print(f'[章节拒绝] {error}')
                resp_extra = None
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in DAILY_COMMANDS or cmd == 17012:
            resp_cmd = cmd + 1
            try:
                if not session or not session.user_data:
                    raise ValueError('未登录')
                request = decode_message(cmd, pb_payload)
                values = use_items(session.user_data, request) if cmd == 17012 else daily_request(session.user_data, cmd, request)
                resp_pb = encode_message(resp_cmd, values)
                pushes = inventory_pushes(session.user_data) + daily_pushes(session.user_data) + [
                    (14009, hero_info_data(session.user_data)), (46011, servant_data(session.user_data)),
                    (32009, profile_data(session.user_data))]
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
                get_user_manager().save_user(session.user_data)
            except ValueError as error:
                print(f'[物品拒绝] 指令={cmd} {error}')
                resp_extra = None
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in (28010, 28014, 28016):
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                request = decode_message(cmd, pb_payload)
                values = claim_task_points(session.user_data, request) if cmd == 28016 else claim_tasks(
                    session.user_data, [request['id']] if cmd == 28010 else request['id_list'])
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
                pushes = inventory_pushes(session.user_data) + [(28001, task_data(session.user_data)), (28019, task_points(session.user_data))]
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
            except ValueError as error:
                print(f'[任务拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in POLYHEDRON_COMMANDS:
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                values = polyhedron_request(session.user_data, cmd, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
                data = polyhedron_data(session.user_data)
                resp_before = [(18001, encode_message(18001, data))]
                if data['game']['state'] == 3:
                    resp_before.append((18005, encode_message(18005, {'end_info': session.user_data.get('polyhedron_settlement', {})})))
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in inventory_pushes(session.user_data)]
            except ValueError as error:
                print(f'[多维变量拒绝] 指令={cmd} {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in CHALLENGE_COMMANDS:
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                values = challenge_request(session.user_data, cmd, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
                pushes = inventory_pushes(session.user_data) + challenge_pushes(session.user_data)
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
            except ValueError as error:
                print(f'[挑战拒绝] 指令={cmd} {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in EQUIP_COMMANDS or cmd in SERVANT_COMMANDS:
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                handler = equip_request if cmd in EQUIP_COMMANDS else servant_request
                values = handler(session.user_data, cmd, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in inventory_pushes(session.user_data)]
                if cmd in SERVANT_COMMANDS:
                    resp_extra.append((46011, encode_message(46011, servant_data(session.user_data)), 0, 0.0))
            except ValueError as error:
                print(f'[装备拒绝] 指令={cmd} {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in LOADOUT_COMMANDS or cmd in (34032, 34034, 34036):
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                request = decode_message(cmd, pb_payload)
                handler = loadout_request if cmd in LOADOUT_COMMANDS else passport_request
                values = handler(session.user_data, cmd, request)
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
                pushes = inventory_pushes(session.user_data)
                if cmd in (34032, 34034, 34036):
                    pushes.append((34031, passport_data(session.user_data)))
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
            except ValueError as error:
                print(f'[存档操作拒绝] 指令={cmd} {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in HERO_COMMANDS:
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                values = hero_request(session.user_data, cmd, decode_message(cmd, pb_payload))
                resp_pb = encode_message(resp_cmd, values)
                get_user_manager().save_user(session.user_data)
            except ValueError as error:
                print(f'[角色操作拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': []} if cmd == 13026 else {'result': 1})
        elif cmd in PROFILE_COMMANDS:
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                values = profile_request(session.user_data, cmd, decode_message(cmd, pb_payload))
                if cmd in (32038, 32132):  # 单向上传布局和当前看板。
                    get_user_manager().save_user(session.user_data)
                    return None
                resp_pb = encode_message(resp_cmd, values)
                if cmd in (32052, 32058):
                    resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in inventory_pushes(session.user_data)]
                get_user_manager().save_user(session.user_data)
            except ValueError as error:
                print(f'[个人资料操作拒绝] {error}')
                if cmd in (32038, 32132):
                    return None
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd in (63000, 63002, 63006, 63008, 63010):
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                save_reserve(session.user_data, cmd, decode_message(cmd, pb_payload))
                get_user_manager().save_user(session.user_data)
                resp_pb = encode_message(resp_cmd, {'result': 0})
            except ValueError as error:
                print(f'[编队操作拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd == 14034:
            selection = bridge.decode_cs_14034(pb_payload)
            user_mgr = get_user_manager()
            user = session.user_data if session and session.user_data else user_mgr.get_or_create_user(account="Developer")
            hero = next((h for h in user.get("heroes", []) if h["id"] == selection["hero_id"]), None)
            skin = selection["skin_id"] or selection["hero_id"]
            valid = hero is not None and skin in hero["skins"]
            if valid:
                hero["skin_id"] = skin
                user_mgr.save_user(user)
            resp_cmd = 14035
            resp_pb = bridge.encode_sc_14035(result=0 if valid else 1)
        elif cmd == 10200:  # cs_10200 -> sc_10201
            resp_cmd = 10201
            resp_pb = bridge.encode_sc_10201()
            print(f"[服务端] 已生成 sc_10201 ({len(resp_pb)} 字节)")
        elif cmd == 10050:  # cs_10050 -> sc_10051
            resp_cmd = 10051
            resp_pb = bridge.encode_sc_10051(state=0)
            print(f"[服务端] 已生成 sc_10051 ({len(resp_pb)} 字节)")
        elif cmd == 10500:  # cs_10500 -> sc_10501
            resp_cmd = 10501
            resp_pb = bridge.encode_sc_10501(result=0)
            if session and session.user_data:
                update_task_progress(session.user_data, 1)
                pushes = daily_pushes(session.user_data) + [(28001, task_data(session.user_data)),
                    (28019, task_points(session.user_data)), (20009, shop_stock(session.user_data))]
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
                get_user_manager().save_user(session.user_data)
            print(f"[服务端] 已生成 sc_10501 ({len(resp_pb)} 字节)")
        elif cmd == 34030:
            user = session.user_data if session else {}
            resp_cmd, resp_pb = 34031, encode_message(34031, passport_data(user))
        elif cmd in (35100, 35102, 35104, 35106, 35108, 35110):
            resp_cmd = cmd + 1
            try:
                if not session:
                    raise ValueError('未登录')
                request = decode_message(cmd, pb_payload)
                values = {'result': 0}
                if cmd == 35108:
                    from equip_exploration import claim_rewards, exploration_pushes
                    values['reward_list'] = claim_rewards(session.user_data, request['id_list'])
                    pushes = inventory_pushes(session.user_data) + exploration_pushes(session.user_data)
                else:
                    pushes = exploration_request(session.user_data, cmd, request)
                get_user_manager().save_user(session.user_data)
                resp_pb = encode_message(resp_cmd, values)
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
            except (ValueError, KeyError) as error:
                print(f'[神域解析拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd == 43002:
            user = session.user_data if session else {}
            resp_cmd, resp_pb = 43003, encode_message(43003, {"result": 0})
            resp_extra = [(43001, encode_message(43001, equip_battle_data(user)), 0, 0.0)]
        elif cmd in (42002, 42004):
            values = enchantment_data(session.user_data if session else {})
            resp_cmd = 42001 if cmd == 42002 else 42005
            if cmd == 42004:
                values = {'result': 0, 'enchantment_battle_list': values['enchantment_battle_list']}
            resp_pb = encode_message(resp_cmd, values)
        elif cmd in (45202, 44010, 44016):
            user = session.user_data if session else {}
            request = decode_message(cmd, pb_payload)
            if cmd == 45202:
                user['boss_mode'] = request['select']
                pushes = boss_data(user)
            else:
                if cmd == 44016:
                    user['mythic_difficulty'] = request['difficulty']
                pushes = [(c, v) for c, v in challenge_pushes(user) if c in (44007, 44009, 44019, 44021, 44023)]
            if session:
                get_user_manager().save_user(user)
            resp_cmd, resp_pb = cmd + 1, encode_message(cmd + 1, {'result': 0})
            resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in pushes]
        elif cmd == 32108:  # cs_32108 -> sc_32109
            resp_cmd = 32109
            resp_pb = bridge.encode_sc_32109(result=0)
            print(f"[服务端] 已生成 sc_32109 ({len(resp_pb)} 字节)")
        elif cmd == 54030:  # cs_54030 -> sc_54031
            resp_cmd = 54031
            try:
                if not session:
                    raise ValueError('未登录')
                battle, player = start_battle(session.user_data, decode_message(cmd, pb_payload))
                player_pb = encode_message(54003, player)
                save_battle_team(session.user_data, battle['common'], battle['config'])
                session.user_data['battle_session'] = battle
                get_user_manager().save_user(session.user_data)
                session.battle = battle
                resp_pb = bridge.encode_sc_54031(result=0)
                resp_extra = [(54003, player_pb, 0, 0.05),
                              (54007, bridge.encode_sc_54007(battle_id=battle['id']), 0, 0.1)]
                print(f"[战斗开始] 类型={battle['common']['type']} 关卡={battle['common']['dest']} ID={battle['id']}")
            except ValueError as error:
                print(f"[战斗拒绝] {error}")
                resp_pb = bridge.encode_sc_54031(result=1)
        elif cmd == 54032:
            request = decode_message(cmd, pb_payload)
            resp_cmd = 54033
            try:
                if not session:
                    raise ValueError('未登录')
                values = settle_battle(session.user_data, session.battle, request['battle_id'])
                session.user_data['battle_session'] = session.battle
                get_user_manager().save_user(session.user_data)
                resp_pb = encode_message(resp_cmd, values)
                resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in inventory_pushes(session.user_data)]
                resp_extra += battle_progress_pushes(session.user_data, session.battle['common']['type'])
                if session.battle['common']['type'] == 52:
                    data = polyhedron_data(session.user_data)
                    resp_before = [(18001, encode_message(18001, data))]
                    if data['game']['state'] == 3:
                        resp_before.append((18005, encode_message(18005, {'end_info': session.user_data.get('polyhedron_settlement', {})})))
                resp_extra += [(c, encode_message(c, v), 0, 0.0) for c, v in
                               ((28001, task_data(session.user_data)), (28019, task_points(session.user_data)))]
            except ValueError as error:
                print(f'[战斗拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd == 54034:
            request = decode_message(cmd, pb_payload)
            resp_cmd = 54035
            try:
                if not session:
                    raise ValueError('未登录')
                session.battle = start_story(request)
                session.battle['id'] = max(session.battle['id'], session.user_data.get('last_battle_id', 0)+1)
                session.user_data['last_battle_id'] = session.battle['id']
                session.user_data['battle_session'] = session.battle
                get_user_manager().save_user(session.user_data)
                resp_pb = encode_message(resp_cmd, {'result': 0, 'battle_id': session.battle['id']})
            except ValueError as error:
                print(f'[剧情拒绝] {error}')
                resp_pb = encode_message(resp_cmd, {'result': 1})
        elif cmd == 19030:  # cs_19030 (Friends list in Chat/Friends view) -> sc_19031
            resp_cmd = 19031
            resp_pb = bridge.encode_sc_19031(result=0)
            print(f"[服务端] 已生成 sc_19031 (完成聊天好友列表加载)")
        elif cmd == 27010:  # cs_27010 (Change/enter chat room) -> sc_27011 + push sc_27005 + sc_27007
            resp_cmd = 27011
            resp_pb = bridge.encode_sc_27011(result=0)
            user_mgr = get_user_manager()
            history = user_mgr.get_recent_world_chat(room_id=1, limit=50)
            resp_extra = [
                (27005, bridge.encode_sc_27005(room_id=1), 0, 0.0),
                (27007, bridge.encode_sc_27007(history), 0, 0.0),
            ]
            print(f"[服务端] 已生成 sc_27011 + sc_27005 (房间 1) + sc_27007 ({len(history)} 条消息)")
        elif cmd == 27012:  # cs_27012 (Request chat history) -> sc_27007
            user_mgr = get_user_manager()
            history = user_mgr.get_recent_world_chat(room_id=1, limit=50)
            resp_cmd = 27007
            resp_pb = bridge.encode_sc_27007(history)
            print(f"[服务端] 已生成 sc_27007 ({len(history)} 条聊天消息)")
        elif cmd == 27014:  # cs_27014 (Send world chat msg) -> sc_27015 + broadcast
            user_mgr = get_user_manager()
            uid = session.user_id if session else 10001
            user = user_mgr.get_user_by_uid(uid) or {"nick": "Player", "icon": 1084, "icon_frame": 2001}
            c_info = bridge.decode_cs_27014(pb_payload)
            content = c_info.get("content", "")
            m_type = c_info.get("type", 1)
            resp_cmd = 27015
            resp_pb = bridge.encode_sc_27015(result=0)
            if content.startswith("$") or content.startswith("/"):
                gm_ok, gm_reply = user_mgr.apply_gm_command(uid, content)
                if gm_ok:
                    sync_online_account(uid)
                    if session and session.writer not in CLIENT_SESSIONS:
                        session.user_data = user_mgr.get_user_by_uid(uid)
                        resp_extra = [(c, encode_message(c, v), 0, 0.0) for c, v in account_pushes(session.user_data)]
                sys_msg = user_mgr.add_world_chat_message(
                    uid=0, nick="GM系统", icon=1084, icon_frame=2001,
                    msg_type=1, content=f"[{'成功' if gm_ok else '错误'}] {gm_reply}", room_id=1
                )
                b_frame = pack_ystcp(27007, bridge.encode_sc_27007([sys_msg]), index=0, server_index=0)
                for s in list(CLIENT_SESSIONS.values()):
                    try:
                        s.writer.write(b_frame)
                    except Exception:
                        pass
            else:
                chat_item = user_mgr.add_world_chat_message(
                    uid=uid, nick=user.get("nick", "Player"), icon=user.get("icon", 1084),
                    icon_frame=user.get("icon_frame", 2001), msg_type=m_type, content=content, room_id=1
                )
                b_frame = pack_ystcp(27007, bridge.encode_sc_27007([chat_item]), index=0, server_index=0)
                for s in list(CLIENT_SESSIONS.values()):
                    try:
                        s.writer.write(b_frame)
                    except Exception:
                        pass
            print(f"[服务端] 已处理聊天消息，UID={uid}: {content[:30]}")
        elif cmd == 27100:  # cs_27100 -> sc_27101
            resp_cmd = 27101
            resp_pb = bridge.encode_sc_27101(result=0)
            print(f"[服务端] 已生成 sc_27101 ({len(resp_pb)} 字节)")
        elif cmd == 19034:  # cs_19034 (Friend private chat msg) -> sc_19035 + sc_19039
            user_mgr = get_user_manager()
            uid = session.user_id if session else 10001
            user = user_mgr.get_user_by_uid(uid) or {"nick": "Player", "icon": 1084, "icon_frame": 2001}
            f_info = bridge.decode_cs_19034(pb_payload)
            rec_uid = f_info.get("receive_uid", 0)
            content = f_info.get("content", "")
            m_type = f_info.get("type", 1)
            msg_item = user_mgr.add_friend_chat_message(
                sender_uid=uid, receiver_uid=rec_uid, nick=user.get("nick", "Player"),
                icon=user.get("icon", 1084), icon_frame=user.get("icon_frame", 2001),
                msg_type=m_type, content=content
            )
            resp_cmd = 19035
            resp_pb = bridge.encode_sc_19035(result=0)
            push_19039 = bridge.encode_sc_19039([msg_item])
            resp_extra = [(19039, push_19039, 0, 0.0)]
            p_frame = pack_ystcp(19039, push_19039, index=0, server_index=0)
            for s in list(CLIENT_SESSIONS.values()):
                if s.user_id == rec_uid and s.writer != writer:
                    try:
                        s.writer.write(p_frame)
                    except Exception:
                        pass
            print(f"[服务端] 好友私聊：发送方 UID={uid} 接收方 UID={rec_uid}")
        elif cmd == 12036:  # cs_12036 -> sc_12037 + sc_12039
            user_mgr = get_user_manager()
            uid = session.user_id if session else 10001
            stk_list = bridge.decode_cs_12036(pb_payload)
            user_mgr.update_custom_stickers(uid, stk_list)
            resp_cmd = 12037
            resp_pb = bridge.encode_sc_12037(result=0)
            resp_extra = [(12039, bridge.encode_sc_12039(stk_list), 0, 0.0)]
            print(f"[服务端] 已更新自定义表情，UID={uid}")
        else:
            mapped = generate_response(cmd, result=0 if cmd in (14042, 32054) else 1)
            if mapped:
                resp_cmd, resp_pb = mapped
                print(f"[服务端未实现] 指令={cmd} -> sc_{resp_cmd} ({len(resp_pb)} 字节)")
            else:
                resp_cmd = cmd + 1
                resp_pb = bridge.encode_sc_generic(resp_cmd, result=1)
                print(f"[服务端默认响应] 已自动生成通用响应 sc_{resp_cmd} 对应 cs_{cmd}")

        if resp_cmd is not None and resp_pb is not None:
            out = pack_ystcp(resp_cmd, resp_pb, is_compress=0, index=c_idx, server_index=c_idx)
            out = b''.join(pack_ystcp(c, pb, index=0, server_index=0) for c, pb in resp_before) + out
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            for extra_cmd, extra_pb, extra_idx, extra_delay in (resp_extra or []):
                frame = pack_ystcp(extra_cmd, extra_pb, is_compress=0, index=extra_idx, server_index=c_idx)
                if extra_delay > 0 and loop is not None and writer is not None:
                    t = loop.create_task(_delayed_send(session, writer, frame, extra_delay))
                    if session:
                        session.add_delayed_task(t)
                else:
                    out += frame
            return out

    return None

def route_http_response(req_str: str, req_body: bytes = b"", headers: dict = None) -> tuple[bytes, str]:
    """分发 SDK、网关和热更新请求，返回响应内容与媒体类型。"""
    parts = req_str.split(" ")
    path = parts[1].split("?")[0] if len(parts) > 1 else "/"
    
    if "/hotfix/" in path or path.endswith(".bytes"):
        filename = Path(path).name
        if "voice_package" in filename:
            return b"", "application/octet-stream"
        return read_hotfix_file(filename), "application/octet-stream"

    if "gateway/get" in path:
        if "action=server" in req_str:
            resp_obj = SERVER_LIST_RESPONSE
        else:
            resp_obj = GATEWAY_RESPONSE
    elif "updateversion/getLatest" in path:
        resp_obj = build_update_response()
    elif "agreementupdate/getLatest" in path:
        resp_obj = AGREEMENT_RESPONSE
    elif "notice/getCurrent" in path:
        resp_obj = NOTICE_RESPONSE
    elif "gamecfg/getInfo" in path:
        resp_obj = GAMECFG_RESPONSE
    elif "sys/time" in path:
        resp_obj = {"code": 0, "errorCode": "0", "message": "success", "data": int(time.time() * 1000)}
    elif "getAgeTip" in path:
        resp_obj = {"code": 0, "errorCode": "0", "message": "success", "data": "16+"}
    elif path == "/sdk-api/pass/captcha/init":
        # SDK 自带离线验证分支，账号密码仍由本地服务端独立校验。
        resp_obj = {"code": 0, "errorCode": "0", "message": "success",
                    "data": {"providerType": "geetest_v3", "clientInitParam": {"offline": True}}}
    elif path == "/sdk-api/auth/user/indulge/getInfo":
        # 本地 Developer 与 SDK 登录的成年模拟账号一致，避免空对象被判定需踢下线。
        resp_obj = {"code": 0, "errorCode": "0", "message": "success",
                    "data": {"adult": True, "age": 18, "playDuration": 0, "remainingTime": 86400}}
    elif "pass/user/" in path or path == '/sdk-api/auth/user/logout':
        resp_obj = sdk_authenticate(req_str, req_body, headers or {}, get_user_manager())
    else:
        resp_obj = {"code": 0, "errorCode": "0", "message": "success", "data": {}}
        
    return json.dumps(resp_obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"

def build_http_response(body_bytes: bytes, content_type: str = "application/json; charset=utf-8", status_code: int = 200, status_text: str = "OK") -> bytes:
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: keep-alive\r\n"
        f"Server: AetherGazerDevServer/1.0\r\n"
        f"Access-Control-Allow-Origin: *\r\n"
        f"\r\n"
    ).encode("ascii")
    return header + body_bytes

async def handle_http_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, first_line_bytes: bytes):
    try:
        first_line = first_line_bytes.decode("latin1").strip()
    except Exception:
        first_line = ""

    if not first_line:
        return

    content_length = 0
    headers = {}
    while True:
        line_bytes = await reader.readline()
        if not line_bytes or line_bytes in (b"\r\n", b"\n"):
            break
        line = line_bytes.decode("latin1", errors="ignore").strip()
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.lower()] = value.strip()
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    req_body = b""
    is_gm = first_line.split(' ')[1].split('?')[0].startswith('/gm')
    if is_gm and (content_length < 0 or content_length > 1024 * 1024):
        error = json.dumps({'error': '请求体超过限制'}, ensure_ascii=False).encode('utf-8')
        writer.write(build_http_response(error, status_code=413, status_text='Payload Too Large').replace(b'Access-Control-Allow-Origin: *\r\n', b''))
        await writer.drain()
        return
    if content_length > 0:
        req_body = await reader.readexactly(content_length)

    print(f"[HTTP 请求] {first_line} (消息体 {len(req_body)} 字节)")
    path = first_line.split(' ')[1].split('?')[0]
    remote = remote_resource_url(Path(path).name) if '/hotfix/' in path and path.endswith('.ys') else None
    if remote:
        await stream_remote_resource(Path(path).name, writer, headers.get('range', ''))
        return
    elif path == '/gm' or path.startswith('/gm/'):
        from gm_admin import gm_response
        resp_body, content_type, status = gm_response(first_line, req_body, headers,
            writer.get_extra_info('peername'), sync_online_account, sync_announcements,
            {s.user_id for s in CLIENT_SESSIONS.values() if s.user_id})
        full_resp = build_http_response(resp_body, content_type, status,
            {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed', 415: 'Unsupported Media Type'}.get(status, 'Error'))
        full_resp = full_resp.replace(b'Access-Control-Allow-Origin: *\r\n', b'Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n')
    else:
        resp_body, content_type = route_http_response(first_line, req_body, headers)
        full_resp = build_http_response(resp_body, content_type=content_type)
    writer.write(full_resp)
    await writer.drain()

async def handle_proxy_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, ssl_ctx: ssl.SSLContext):
    peer = writer.get_extra_info("peername")
    try:
        first_line_bytes = await reader.readline()
        if not first_line_bytes:
            return
        first_line = first_line_bytes.decode("latin1", errors="ignore").strip()

        if first_line.startswith("CONNECT "):
            authority = first_line.split(' ')[1]
            while True:
                h = await reader.readline()
                if not h or h in (b"\r\n", b"\n"):
                    break

            if is_resource_cdn(authority):
                await tunnel_resource_cdn(authority, reader, writer)
                return

            if ssl_ctx is None:
                writer.write(build_http_response(b'', status_code=403, status_text='Forbidden'))
                await writer.drain()
                return

            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            loop = asyncio.get_running_loop()
            protocol = writer.transport.get_protocol()
            new_transport = await loop.start_tls(writer.transport, protocol, ssl_ctx, server_side=True)
            writer._transport = new_transport

            while True:
                inner_line = await reader.readline()
                if not inner_line:
                    break
                await handle_http_request(reader, writer, inner_line)
        else:
            await handle_http_request(reader, writer, first_line_bytes)
            while True:
                next_line = await reader.readline()
                if not next_line:
                    break
                await handle_http_request(reader, writer, next_line)
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    except Exception as e:
        print(f"[HTTP／代理错误] {peer}: {e}")
    finally:
        session = CLIENT_SESSIONS.get(writer)
        if session:
            session.close()
        CLIENT_SESSIONS.pop(writer, None)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def handle_direct_https(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            await handle_http_request(reader, writer, line)
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    except Exception as e:
        print(f"[HTTPS 错误] {peer}: {e}")
    finally:
        session = CLIENT_SESSIONS.get(writer)
        if session:
            session.close()
        CLIENT_SESSIONS.pop(writer, None)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def _delayed_send(session: Optional[ClientSession], writer: asyncio.StreamWriter, frame: bytes, delay: float):
    """按推送配置指定的延迟向当前连接发送响应帧。"""
    try:
        await asyncio.sleep(delay)
        if session and session.closed:
            return
        writer.write(frame)
        await writer.drain()
        # Only log sizable frames - the many small rolling no-op frames
        # (sc_32055 keepalive etc.) would otherwise flood the console.
        if len(frame) >= 512:
            print(f"[服务端延迟推送] 延迟 {delay} 秒后已推送帧（{len(frame)} 字节）")
    except asyncio.CancelledError:
        pass
    except Exception:
        pass

async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """按客户端 Protocol.Pack 的 uint32 小端长度读取连续请求，响应使用 YSTcp 格式。"""
    peer = writer.get_extra_info("peername")
    print(f"[TCP 连接] 新游戏客户端已连接，地址： {peer}")
    session = ClientSession(writer, peer)
    CLIENT_SESSIONS[writer] = session
    try:
        while True:
            size_bytes = await reader.readexactly(4)
            packet_size = struct.unpack("<I", size_bytes)[0]
            if packet_size < 3 or packet_size > 65535:
                print(f"[TCP 错误] 无效的数据包长度 ({packet_size}) 来自 {peer}, 关闭连接。")
                break
            payload = await reader.readexactly(packet_size)
            if payload[0] in (7, 8):
                # 游戏协议：[flag u8][cmd u32 LE][index u16 LE][ack u16 LE][protobuf]。
                resp = handle_tcp_message(2048, 0, 0, payload[1:], writer=writer, session=session)
            else:
                flag, opcode, rpc_id, body = unpack_packet_payload(payload)
                print(f"[TCP 原生消息] 标志={flag} 操作码={opcode} RPC={rpc_id} 字节数={len(body)}")
                resp = handle_tcp_message(opcode, flag, rpc_id, body, writer=writer, session=session)
            if resp is not None:
                writer.write(resp)
                await writer.drain()
    except asyncio.IncompleteReadError:
        print(f"[TCP 断开] 客户端 {peer} 已断开连接（EOF）。")
    except Exception as e:
        print(f"[TCP 错误] 客户端 {peer}：{e}")
    finally:
        session.close()
        CLIENT_SESSIONS.pop(writer, None)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

def _self_test():
    test_body = b"normal payload"
    p1 = pack_packet(100, test_body, flag=0)
    p1_size = struct.unpack("<H", p1[:2])[0]
    assert p1_size == 3 + len(test_body)
    f1, op1, rpc1, b1 = unpack_packet_payload(p1[2:])
    assert f1 == 0 and op1 == 100 and rpc1 == 0 and b1 == test_body

    p2 = pack_packet(102, test_body, flag=1, rpc_id=999)
    p2_size = struct.unpack("<H", p2[:2])[0]
    assert p2_size == 7 + len(test_body)
    f2, op2, rpc2, b2 = unpack_packet_payload(p2[2:])
    assert f2 == 1 and op2 == 102 and rpc2 == 999 and b2 == test_body

    c_time = 1712345678901
    ping_payload = b"\x08" + encode_varint(c_time)
    assert decode_ping(ping_payload) == c_time
    pong_resp = handle_tcp_message(100, 0, 0, ping_payload)
    assert pong_resp is not None

    # 未认证请求不得获得默认账号的游戏存档。
    for command in (10038, 10042):
        response = handle_tcp_message(2048, 0, 0, struct.pack("<IHH", command, 1, 0))
        _, reply, _, _, payload = unpack_ystcp(response[2:])
        assert reply == command + 1 and decode_message(reply, payload, 'sc')['result'] != 0

    # Test getAgeTip HTTP route returns string data
    age_tip_bytes, _ = route_http_response("GET /mix-sdk-api/pass/game/channelext/getAgeTip HTTP/1.1")
    age_tip_obj = json.loads(age_tip_bytes.decode("utf-8"))
    assert age_tip_obj["code"] == 0 and isinstance(age_tip_obj["data"], str)

    print("[自检] ET、YSTcp 和 Tolua ProtoBridge 自检通过。")

async def main():
    """启动本地 HTTP 与游戏服务，按配置选择是否启用旧 HTTPS 网关。"""
    # 1. 环境与依赖自检
    is_ok, issues = validate_environment()
    for issue in issues:
        print(issue)
    if not is_ok:
        print("\n[服务端致命错误] 环境检查未通过，服务已终止启动。请根据上述提示修正后重试。")
        sys.exit(1)

    # 2. 协议与编解码自测
    _self_test()

    # 3. 加载 HTTPS 证书
    ssl_ctx = None
    if ENABLE_HTTPS:
        try:
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(certfile=str(CERT_FILE), keyfile=str(KEY_FILE))
        except Exception as e:
            print(f"\n[服务端致命错误] 加载 HTTPS 证书失败 ({CERT_FILE}): {e}")
            print("请提供配置中的证书文件；默认使用无需证书的接入方式。")
            sys.exit(1)

    # 4. 启动 HTTP / CONNECT 代理服务
    try:
        proxy_server = await asyncio.start_server(
            lambda r, w: handle_proxy_client(r, w, ssl_ctx),
            HOST,
            HTTP_PROXY_PORT
        )
        print(f"[服务端] HTTP/CONNECT 代理正在监听 {HOST}:{HTTP_PROXY_PORT}")
    except OSError as e:
        print(f"\n[服务端致命错误] 无法绑定 HTTP 代理端口 {HOST}:{HTTP_PROXY_PORT}: {e}")
        print("可能原因: 端口已被其他进程占用 (如 Fiddler, Charles 或系统其他代理)。")
        print("解决方式: 请关闭冲突程序，或在 config.py 中修改 HTTP_PROXY_PORT。\n")
        sys.exit(1)

    # 5. 启动直连 HTTPS 网关（用于 hosts 重定向模式）
    https_server = None
    if ENABLE_HTTPS:
        try:
            https_server = await asyncio.start_server(handle_direct_https, HOST, HTTPS_DIRECT_PORT, ssl=ssl_ctx)
            print(f"[服务端] 直连 HTTPS 网关正在监听 {HOST}:{HTTPS_DIRECT_PORT}")
        except OSError as e:
            print(f"[服务端警告] 无法绑定直连 HTTPS 端口 {HOST}:{HTTPS_DIRECT_PORT}: {e}")

    # 6. 启动游戏 TCP 网关
    try:
        tcp_server = await asyncio.start_server(
            handle_tcp_client,
            HOST,
            TCP_GATEWAY_PORT
        )
        print(f"[服务端] 游戏 TCP 网关正在监听 {HOST}:{TCP_GATEWAY_PORT}")
    except OSError as e:
        print(f"\n[服务端致命错误] 无法绑定游戏 TCP 端口 {HOST}:{TCP_GATEWAY_PORT}: {e}")
        print("可能原因: 端口已被占用。请终止占用进程，或在 config.py 中修改 TCP_GATEWAY_PORT。\n")
        sys.exit(1)

    udp_transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: BattleUDP(handle_native_battle), local_addr=(HOST, TCP_GATEWAY_PORT))
    print(f"[服务端] 战斗 UDP 正在监听 {HOST}:{TCP_GATEWAY_PORT}")
    print("[服务端] 全部服务已就绪，等待连接……")

    tasks = [proxy_server.serve_forever(), tcp_server.serve_forever(), publish_scheduled_announcements()]
    if https_server:
        tasks.append(https_server.serve_forever())
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # 重定向日志同样使用 UTF-8，避免中文输出被系统代码页错误解码。
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[服务端] 收到关闭请求。")
