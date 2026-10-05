# -*- coding: utf-8 -*-
"""
Aether Gazer 用户数据与聊天持久化管理器 (UserManager)
支持：
- 多账号密码认证与独立数据持久化 (data/users/{uid}.json)
- 世界聊天历史记录持久化 (data/chat/world_chat.json)
- 好友私聊历史记录持久化 (data/chat/friend_chat.json)
- 自定义表情包配置持久化
- 线程安全读写与原子写入 (.tmp -> rename)
"""

import json
import os
from pathlib import Path
import threading
import time
import secrets
from account_auth import password_record, password_matches
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_DIR = DATA_DIR / "users"
CHAT_DIR = DATA_DIR / "chat"
META_FILE = USERS_DIR / "meta.json"
CHAT_FILE = CHAT_DIR / "world_chat.json"
FRIEND_CHAT_FILE = CHAT_DIR / "friend_chat.json"

DEFAULT_STICKERS = list(range(1, 17))


class UserManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(UserManager, cls).__new__(cls)
                cls._instance._init_storage()
        return cls._instance

    def _init_storage(self):
        USERS_DIR.mkdir(parents=True, exist_ok=True)
        CHAT_DIR.mkdir(parents=True, exist_ok=True)

        if not META_FILE.exists():
            meta = {
                "next_uid": 10001,
                "next_msg_id": 1,
                "accounts": {},
                "tokens": {}
            }
            self._save_json(META_FILE, meta)

        if not CHAT_FILE.exists():
            self._save_json(CHAT_FILE, [])
        if not FRIEND_CHAT_FILE.exists():
            self._save_json(FRIEND_CHAT_FILE, [])

        # 确保默认账号 10001 存在
        if not any(name.casefold() == 'developer' for name in self.get_meta().get('accounts', {})):
            self.get_or_create_user(account="Developer", default_nick="Developer")

    def _load_json(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[存储错误] 加载 {path} 失败：{e}")
        return default

    def _save_json(self, path: Path, data: Any):
        """原子保存并将写入失败交给调用方，避免向客户端报告虚假成功。"""
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if path.exists():
                os.replace(tmp, path)
            else:
                os.rename(tmp, path)
        except Exception as e:
            print(f"[存储错误] 保存 {path} 失败：{e}")
            raise

    def get_meta(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_json(META_FILE, {
                "next_uid": 10001,
                "next_msg_id": 1,
                "accounts": {},
                "tokens": {}
            })

    def _save_meta(self, meta: Dict[str, Any]):
        self._save_json(META_FILE, meta)

    def get_or_create_user(self, account: str, token: Optional[str] = None, default_nick: Optional[str] = None) -> Dict[str, Any]:
        """恢复既有存档；普通新账号使用初始白号，Developer 保留开发模板。"""
        with self._lock:
            meta = self._load_json(META_FILE, {
                "next_uid": 10001,
                "next_msg_id": 1,
                "accounts": {},
                "tokens": {}
            })
            accounts = meta.setdefault("accounts", {})
            tokens = meta.setdefault("tokens", {})

            if account in accounts:
                uid = accounts[account]
                user_file = USERS_DIR / f"{uid}.json"
                user_data = self._load_json(user_file, None)
                if user_data:
                    changed = False
                    if token and user_data.get("token") != token:
                        old_token = user_data.get("token")
                        if old_token and old_token in tokens:
                            del tokens[old_token]
                        user_data["token"] = token
                        tokens[token] = uid
                        changed = True
                    user_data["last_login_at"] = int(time.time())
                    changed = True
                    if changed:
                        self._save_meta(meta)
                        self._save_json(user_file, user_data)
                    return user_data

            uid = meta.get("next_uid", 10001)
            meta["next_uid"] = uid + 1

            now_ts = int(time.time())
            if not token:
                token = secrets.token_urlsafe(32)

            nick = default_nick if default_nick else (account if account else f"User_{uid}")

            user_data = {
                "uid": uid,
                "account": account,
                "token": token,
                "nick": nick,
                "level": 80,
                "exp": 0,
                "gold": 99999999,
                "diamond": 999999,
                "stamina": 240,
                "icon": 1084,
                "icon_frame": 2001,
                "custom_stickers": list(DEFAULT_STICKERS),
                "created_at": now_ts,
                "last_login_at": now_ts
            }
            if account.casefold() != 'developer':
                from account_defaults import new_account_defaults
                user_data.update(new_account_defaults())

            accounts[account] = uid
            tokens[token] = uid
            self._save_meta(meta)
            self._save_json(USERS_DIR / f"{uid}.json", user_data)
            return user_data

    def get_user_by_uid(self, uid: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            user_file = USERS_DIR / f"{uid}.json"
            return self._load_json(user_file, None)

    def authenticate_password(self, account: str, password: str) -> Dict[str, Any]:
        """校验已有密码或自动注册；旧无密码存档首次登录时绑定密码。"""
        if not isinstance(account, str) or not account.strip() or len(account.strip()) > 64:
            raise ValueError('账号须为 1 至 64 个字符')
        account = account.strip()
        if any(ord(char) < 32 for char in account) or not isinstance(password, str) or not 1 <= len(password) <= 256:
            raise ValueError('账号或密码格式错误，密码须为 1 至 256 个字符')
        with self._lock:
            meta = self.get_meta()
            account = next((name for name in meta['accounts'] if name.casefold() == account.casefold()), account)
            uid = meta['accounts'].get(account)
            user = self.get_user_by_uid(uid) if uid else None
            if user and user.get('password_auth') and not password_matches(password, user['password_auth']):
                raise ValueError('账号或密码错误')
            if not user:
                user = self.get_or_create_user(account)
                meta = self.get_meta()
            if not user.get('password_auth'):
                user['password_auth'] = password_record(password)
            meta['tokens'].pop(user.get('token'), None)
            user['token'] = secrets.token_urlsafe(32)
            user['nick'] = user['account']
            user['last_login_at'] = int(time.time())
            meta['tokens'][user['token']] = user['uid']
            self.save_user(user)
            self._save_meta(meta)
            return user

    def authenticate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """只接受已绑定密码且与存档一致的有效随机令牌。"""
        if not isinstance(token, str) or not token:
            return None
        with self._lock:
            uid = self.get_meta().get('tokens', {}).get(token)
            user = self.get_user_by_uid(uid) if uid else None
            return user if user and user.get('password_auth') and secrets.compare_digest(user.get('token', ''), token) else None

    def revoke_token(self, token: str):
        """退出登录时撤销当前令牌，保留账号密码与游戏存档。"""
        with self._lock:
            meta = self.get_meta()
            if token in meta['tokens']:
                user = self.get_user_by_uid(meta['tokens'][token])
                if user and user.get('token') == token:
                    user['token'] = ''
                    self.save_user(user)
                del meta['tokens'][token]
                self._save_meta(meta)

    def save_user(self, user_data: Dict[str, Any]):
        with self._lock:
            uid = user_data.get("uid")
            if uid:
                user_file = USERS_DIR / f"{uid}.json"
                self._save_json(user_file, user_data)

    def modify_currency(self, uid: int, gold: Optional[int] = None, diamond: Optional[int] = None,
                        stamina: Optional[int] = None, level: Optional[int] = None,
                        flower: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """修改明确的核心余额；移转之花指令设置客户端显示的三平台合计。"""
        with self._lock:
            user = self.get_user_by_uid(uid)
            if not user:
                return None
            if gold is not None:
                user['gold'] = max(0, int(gold))
                user.setdefault('currencies', {})['2'] = user['gold']
            if diamond is not None:
                user['diamond'] = max(0, int(diamond))
                user.setdefault('currencies', {})['1'] = user['diamond']
            if stamina is not None:
                user['stamina'] = max(0, int(stamina))
                user.setdefault('currencies', {})['4'] = user['stamina']
            if level is not None:
                user['level'] = max(1, min(100, int(level)))
            if flower is not None:
                for item, field, value in ((31, 'flower', flower), (30, 'flower_ios', 0), (32, 'flower_free', 0)):
                    user[field] = max(0, int(value))
                    user.setdefault('currencies', {})[str(item)] = user[field]
            self.save_user(user)
            return user

    def apply_gm_command(self, uid: int, cmd_str: str) -> tuple[bool, str]:
        """串行执行 GM 指令，发放与保存失败不会被报告为成功。"""
        with self._lock:
            return self._apply_gm_command(uid, cmd_str)

    def _apply_gm_command(self, uid: int, cmd_str: str) -> tuple[bool, str]:
        """解析聊天及网页共用指令，只接受完整且有效的参数。"""
        cmd_str = cmd_str.strip()
        if cmd_str.startswith('$') or cmd_str.startswith('/'):
            cmd_str = cmd_str[1:].strip()
        parts = cmd_str.split()
        if not parts:
            return False, 'GM 指令为空'

        cmd_type = parts[0].lower()
        args = parts[1:]

        user = self.get_user_by_uid(uid)
        if not user:
            return False, f'未找到用户 {uid}'

        if cmd_type == 'unlock':
            if args != ['character']:
                return False, '用法：/unlock character'
            from account_unlocks import unlock_characters
            unlock_characters(user)
            self.save_user(user)
            return True, f"已解锁 {len(user['heroes'])} 名满配角色、全部皮肤与场景（含额外视角），配满级刻印、满阶专属钥从"

        if cmd_type == 'give':
            if len(args) != 2 or not all(arg.isdigit() for arg in args):
                return False, '用法：/give [物品ID] [数量]'
            try:
                from item_catalog import give_items, item_catalog
                item, amount = map(int, args)
                give_items(user, [{'id': item, 'num': amount}])
                self.save_user(user)
                return True, f"已发放 {item_catalog()[item]['name']}（{item}）×{amount}"
            except (ValueError, KeyError) as error:
                return False, str(error)

        if cmd_type in ('flower', 'flowers'):
            if len(args) != 1 or not args[0].isdigit() or int(args[0]) > 2_000_000_000:
                return False, '用法：/flower [0 至 2000000000 的整数]'
            self.modify_currency(uid, flower=int(args[0]))
            return True, f'移转之花合计已设为 {args[0]}'

        if cmd_type not in ('gold', 'money', 'diamond', 'diamonds', 'level', 'lvl', 'stamina', 'energy', 'help', '?'):
            return False, f'未知 GM 指令：{cmd_type}'

        if cmd_type not in ('help', '?') and (len(args) != 1 or not args[0].isdigit() or int(args[0]) > 2_000_000_000):
            return False, '设置指令需要一个 0 至 2000000000 的整数参数'

        if cmd_type in ('gold', 'money'):
            if not args or not args[0].lstrip('-').isdigit():
                return False, '用法：$gold <整数>'
            amt = int(args[0])
            self.modify_currency(uid, gold=amt)
            return True, f'金币已设为 {max(0, amt)}'

        elif cmd_type in ('diamond', 'diamonds'):
            if not args or not args[0].lstrip('-').isdigit():
                return False, '用法：$diamond <整数>'
            amt = int(args[0])
            self.modify_currency(uid, diamond=amt)
            return True, f'移转之辉已设为 {max(0, amt)}'

        elif cmd_type in ('level', 'lvl'):
            if not args or not args[0].isdigit():
                return False, '用法：$level <1–100 的整数>'
            lvl = int(args[0])
            self.modify_currency(uid, level=lvl)
            return True, f'玩家等级已设为 {max(1, min(100, lvl))}'

        elif cmd_type in ('stamina', 'energy'):
            if not args or not args[0].isdigit():
                return False, '用法：$stamina <非负整数>'
            sta = int(args[0])
            self.modify_currency(uid, stamina=sta)
            return True, f'体力已设为 {sta}'

        elif cmd_type in ('help', '?'):
            return True, '可用 GM 指令：/unlock character、/give [物品ID] [数量]、/gold [数量]、/diamond [数量]、/flower [数量]、/level [1–100]、/stamina [数量]、/help；也支持 $ 前缀'

        return False, f'未知 GM 指令：{cmd_type}'

    def update_custom_stickers(self, uid: int, stickers: List[int]):
        with self._lock:
            user_file = USERS_DIR / f"{uid}.json"
            user_data = self._load_json(user_file, None)
            if user_data:
                user_data["custom_stickers"] = stickers
                self._save_json(user_file, user_data)

    def add_world_chat_message(self, uid: int, nick: str, icon: int, icon_frame: int,
                               msg_type: int, content: str, room_id: int = 1) -> Dict[str, Any]:
        with self._lock:
            meta = self._load_json(META_FILE, {"next_msg_id": 1})
            msg_id = meta.get("next_msg_id", 1)
            meta["next_msg_id"] = msg_id + 1
            self._save_meta(meta)

            chat_item = {
                "msg_id": msg_id,
                "uid": uid,
                "nick": nick,
                "icon": icon,
                "icon_frame": icon_frame,
                "type": msg_type,
                "content": content,
                "timestamp": int(time.time()),
                "room_id": room_id,
                "ip_location": "本地",
                "chat_bubble": (self.get_user_by_uid(uid) or {}).get('profile', {}).get('chat_bubble', 9001)
            }

            history = self._load_json(CHAT_FILE, [])
            history.append(chat_item)
            if len(history) > 500:
                history = history[-500:]
            self._save_json(CHAT_FILE, history)
            return chat_item

    def get_recent_world_chat(self, room_id: Optional[int] = 1, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            history = self._load_json(CHAT_FILE, [])
            if room_id is not None:
                history = [m for m in history if m.get('room_id') == room_id]
            return history[-limit:]

    def add_friend_chat_message(self, sender_uid: int, receiver_uid: int, nick: str,
                               icon: int, icon_frame: int, msg_type: int, content: str) -> Dict[str, Any]:
        with self._lock:
            meta = self._load_json(META_FILE, {"next_msg_id": 1})
            msg_id = meta.get("next_msg_id", 1)
            meta["next_msg_id"] = msg_id + 1
            self._save_meta(meta)

            chat_item = {
                "msg_id": msg_id,
                "uid": sender_uid,
                "receive_uid": receiver_uid,
                "nick": nick,
                "icon": icon,
                "icon_frame": icon_frame,
                "type": msg_type,
                "content": content,
                "timestamp": int(time.time()),
                "ip_location": "本地",
                "chat_bubble": (self.get_user_by_uid(sender_uid) or {}).get('profile', {}).get('chat_bubble', 9001)
            }

            history = self._load_json(FRIEND_CHAT_FILE, [])
            history.append(chat_item)
            if len(history) > 200:
                history = history[-200:]
            self._save_json(FRIEND_CHAT_FILE, history)
            return chat_item

    def get_recent_friend_chat(self, uid1: int, uid2: int, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            history = self._load_json(FRIEND_CHAT_FILE, [])
            filtered = [
                m for m in history
                if (m.get("uid") == uid1 and m.get("receive_uid") == uid2) or
                   (m.get("uid") == uid2 and m.get("receive_uid") == uid1)
            ]
            return filtered[-limit:]


def get_user_manager() -> UserManager:
    return UserManager()
