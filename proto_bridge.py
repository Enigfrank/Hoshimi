from runtime_data import load_runtime_table
from typing import Any

import ctypes
import os
import struct
import time
from pathlib import Path

from currency_data import NATIVE_CURRENCY_IDS, MATERIAL_TOKEN_IDS, build_currency_balances

from config import BASE_DIR, TOLUA_PATH, LUA_SRC_DIR

from activity_data import build_available_activities
from hero_data import HERO_LOADOUTS


ALL_GUIDE_IDS = load_runtime_table("ALL_GUIDE_IDS")

ALL_WEAK_GUIDE_IDS = load_runtime_table("ALL_WEAK_GUIDE_IDS")

def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

class ToluaBridge:
    def __init__(self):
        if not TOLUA_PATH.exists():
            raise FileNotFoundError(f"tolua.dll 未找到，路径： {TOLUA_PATH}")
        self.dll = ctypes.CDLL(str(TOLUA_PATH))
        self._setup_c_api()
        self._init_lua_state()

    def _setup_c_api(self):
        self.dll.luaL_newstate.restype = ctypes.c_void_p
        self.dll.luaL_openlibs.argtypes = [ctypes.c_void_p]
        self.dll.luaopen_pb.argtypes = [ctypes.c_void_p]
        self.dll.luaopen_pb.restype = ctypes.c_int
        self.dll.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
        self.dll.luaL_loadbuffer.restype = ctypes.c_int
        self.dll.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.dll.lua_pcall.restype = ctypes.c_int
        self.dll.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
        self.dll.lua_tolstring.restype = ctypes.c_void_p
        self.dll.lua_settop.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.dll.lua_getfield.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        self.dll.lua_setfield.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        self.dll.lua_pushlstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]

    def _init_lua_state(self):
        self.L = self.dll.luaL_newstate()
        assert self.L, "创建 Lua 状态失败"
        self.dll.luaL_openlibs(self.L)

        # Register C pb module
        self.dll.lua_getfield(self.L, -10002, b"package")
        self.dll.lua_getfield(self.L, -1, b"loaded")
        self.dll.luaopen_pb(self.L)
        self.dll.lua_setfield(self.L, -2, b"pb")
        self.dll.lua_settop(self.L, 0)

        # Custom loader to resolve any filename without path prefix
        lua_dir_esc = str(LUA_SRC_DIR).replace("\\", "/")
        init_script = f"""
table.insert(package.loaders or package.searchers, 1, function(name)
    local basename = name:match("[^/]+$") or name
    local candidates = {{
        "{lua_dir_esc}/" .. basename .. ".lua",
        "{lua_dir_esc}/" .. basename .. ".lua.bytes",
        "{lua_dir_esc}/" .. name .. ".lua",
        "{lua_dir_esc}/" .. name .. ".lua.bytes"
    }}
    for _, path in ipairs(candidates) do
        local f = io.open(path, "rb")
        if f then
            f:close()
            return loadfile(path)
        end
    end
end)

_G.p10 = require("p10_pb")
_G.p11 = require("p11_pb")
_G.p12 = require("p12_pb")
_G.p13 = require("p13_pb")
_G.p14 = require("p14_pb")
_G.p15 = require("p15_pb")
_G.p16 = require("p16_pb")
_G.p17 = require("p17_pb")
_G.p19 = require("p19_pb")
_G.p20 = require("p20_pb")
_G.p23 = require("p23_pb")
_G.p28 = require("p28_pb")
_G.p24 = require("p24_pb")
_G.p30 = require("p30_pb")
_G.p32 = require("p32_pb")
_G.p46 = require("p46_pb")
_G.p54 = require("p54_pb")
_G.p59 = require("p59_pb")
_G.p27 = require("p27_pb")

setmetatable(_G, {{
    __index = function(t, key)
        if type(key) == "string" and key:match("^p%d+$") then
            local ok, mod = pcall(require, key .. "_pb")
            if ok and mod then
                rawset(t, key, mod)
                return mod
            end
        end
        return nil
    end
}})
""".encode("utf-8")

        err = self.dll.luaL_loadbuffer(self.L, init_script, len(init_script), b"init_bridge")
        if err != 0:
            err_msg = self._get_error_msg()
            raise RuntimeError(f"Lua 初始化错误: {err_msg}")
        err = self.dll.lua_pcall(self.L, 0, 0, 0)
        if err != 0:
            err_msg = self._get_error_msg()
            raise RuntimeError(f"Lua 初始化 p调用 错误: {err_msg}")

    def _get_error_msg(self) -> str:
        size = ctypes.c_size_t(0)
        ptr = self.dll.lua_tolstring(self.L, -1, ctypes.byref(size))
        if ptr:
            return ctypes.string_at(ptr, size.value).decode("utf-8", errors="ignore")
        return "未知错误"

    def run_lua_expr(self, expr: str) -> bytes:
        script = f"local ret = {expr}\nreturn ret".encode("utf-8")
        err = self.dll.luaL_loadbuffer(self.L, script, len(script), b"eval")
        if err != 0:
            err_msg = self._get_error_msg()
            raise RuntimeError(f"loadbuffer 错误: {err_msg}")
        err = self.dll.lua_pcall(self.L, 0, 1, 0)
        if err != 0:
            err_msg = self._get_error_msg()
            raise RuntimeError(f"p调用 错误: {err_msg}")
        
        size = ctypes.c_size_t(0)
        ptr = self.dll.lua_tolstring(self.L, -1, ctypes.byref(size))
        res = ctypes.string_at(ptr, size.value) if ptr else b""
        self.dll.lua_settop(self.L, 0)
        return res

    def encode_sc_10039(self, result: int = 0, server_id: int = 1, ip: str = "127.0.0.1", port: int = 5001,
                        user_id: int = 10001, gstoken: str = "dev_mock_token_12345", timestamp: int = None,
                        is_new_player: int = 0) -> bytes:
        if timestamp is None:
            timestamp = int(time.time())
        expr = f"""(function()
            local m = _G.p10.sc_10039()
            m.result = {result}
            m.server_id = {server_id}
            m.ip = "{ip}"
            m.port = {port}
            m.user_id = {user_id}
            m.gstoken = "{gstoken}"
            m.timestamp = {timestamp}
            m.is_new_player = {is_new_player}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_10043(self, result: int = 0, register_timestamp: int = None, timestamp: int = None,
                        verify_timestamp: int = None, uid_sign: str = "mock_uid_sign") -> bytes:
        """登录时间同步使用固定 UTC+8 周一锚点。"""
        now = int(time.time())
        if register_timestamp is None:
            register_timestamp = now
        if timestamp is None:
            timestamp = now
        if verify_timestamp is None:
            verify_timestamp = 4 * 86400 - 8 * 3600
        expr = f"""(function()
            local m = _G.p10.sc_10043()
            m.result = {result}
            m.register_timestamp = {register_timestamp}
            m.timestamp = {timestamp}
            m.verify_timestamp = {verify_timestamp}
            m.uid_sign = "{uid_sign}"
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_10201(self, timestamp: int = None) -> bytes:
        """同步绝对时间与固定的 UTC+8 周一锚点，供客户端换算服务器时区。"""
        now = int(time.time()) if timestamp is None else timestamp
        monday_0oclock = 4 * 86400 - 8 * 3600
        expr = f"""(function()
            local m = _G.p10.sc_10201()
            m.timestamp = {now}
            m.monday_0oclock_timestamp = {monday_0oclock}
            m.verify_timestamp = {monday_0oclock}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_10051(self, state: int = 0) -> bytes:
        """心跳沿用登录的服务器时区锚点，避免把大厅时间重置为零点。"""
        now = int(time.time())
        expr = f"""(function()
            local m = _G.p10.sc_10051()
            m.state = {state}
            m.timestamp = {now}
            m.verify_timestamp = {4 * 86400 - 8 * 3600}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_10600(self, open_system_ids: list[int] | None = None) -> bytes:
        """Encode sc_10600 (open system list init).

        SystemData:GetSystemIsOpen only returns true for ids present in this
        list; a missing/empty push locks every system ("function not open").
        """
        # 当前客户端新增的玩法 ID 不在旧静态清单中，必须以本机配置为准。
        ids = '''(function()
            local c=require('SystemCfg');local result={};local seen={}
            local function add(id) if c[id] and not seen[id] then seen[id]=true;result[#result+1]=id end end
            for _,id in ipairs(c.all) do add(id) end
            local chapters=require('ChapterClientCfg')
            for _,id in ipairs(chapters.all) do
                local jump=chapters[id].jump_system
                if type(jump)=='table' then add(jump[1]) end
            end
            return result
        end)()''' if open_system_ids is None else '{' + ','.join(str(i) for i in open_system_ids) + '}'
        expr = f"""(function()
            local m = _G.p10.sc_10600()
            local ids = {ids}
            for _, v in ipairs(ids) do
                m.open_system:append(v)
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_24009(self, stage_ids: list[int] | None = None,
                        clear_times: int = 1, stars: int = 3) -> bytes:
        """按当前客户端的有效星级条件编码主线进度，三星表示三项 1。"""
        from battle_progress import progress_catalog
        from gameplay_protocol import encode_message
        counts = {cfg['id']: cfg['star_count'] for cfg in progress_catalog()['story']}
        ids = stage_ids if stage_ids is not None else counts
        return encode_message(24009, {'user_chapter_list': [
            {'id': stage, 'clear_times': clear_times,
             'star_list': [int(i <= min(stars, counts[stage])) for i in (1, 2, 3)]}
            for stage in ids]})

    def encode_sc_24017(self) -> bytes:
        """Encode sc_24017 (main chapter star reward claim list, empty = none claimed)."""
        expr = """(function()
            local m = _G.p24.sc_24017()
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_10501(self, result: int = 0) -> bytes:
        """跨日同步沿用 UTC+8 锚点。"""
        now = int(time.time())
        from shop_transactions import period_end
        next_day = period_end(4, now)
        next_week = period_end(3, now)
        next_month = period_end(2, now)
        expr = f"""(function()
            local m = _G.p10.sc_10501()
            m.result = {result}
            m.timestamp = {now}
            m.verify_timestamp = {4 * 86400 - 8 * 3600}
            m.next_refresh_time = {next_day}
            m.next_weekly_refresh_time = {next_week}
            m.next_monthly_refresh_time = {next_month}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_11001(self, activities: list[dict] | None = None) -> bytes:
        """初始化当前资源版本的主活动和子活动，使用配置中的主题与模板。"""
        now = int(time.time())
        if activities is None:
            activities = build_available_activities()
        entries = []
        for a in activities:
            subs = ",".join(str(s) for s in (a.get("sub_activity_id_list") or []))
            entries.append(
                "{activity_id=%d,start_time=%d,stop_time=%d,state=%d,theme=%d,template=%d,sub_activity_id_list={%s}}"
                % (a["activity_id"],
                   a.get("start_time", now - 7 * 86400),
                   a.get("stop_time", now + 5 * 365 * 86400),
                   a.get("state", 1),
                   a.get("theme", 0),
                   a.get("template", 0),
                   subs)
            )
        list_lit = ";".join(entries)
        expr = f"""(function()
            local m = _G.p11.sc_11001()
            local l = {{{list_lit}}}
            for i = 1, #l do
                local e = m.activity_list:add()
                e.activity_id = l[i].activity_id
                e.start_time = l[i].start_time
                e.stop_time = l[i].stop_time
                e.state = l[i].state
                e.theme = l[i].theme
                e.template = l[i].template
                for j = 1, #(l[i].sub_activity_id_list or {{}}) do
                    e.sub_activity_id_list:append(l[i].sub_activity_id_list[j])
                end
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_12011(self, guide_list: list[int] | None = None) -> bytes:
        """Encode sc_12011 (completed guide id list)."""
        guide_list = guide_list if guide_list is not None else ALL_GUIDE_IDS
        subs_lit = ",".join(str(s) for s in guide_list)
        expr = f"""(function()
            local m = _G.p12.sc_12011()
            for _, v in ipairs({{{subs_lit}}}) do
                m.mod_guide_list:append(v)
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_12111(self, guide_list: list[int] | None = None) -> bytes:
        """Encode sc_12111 (completed weak guide id list)."""
        guide_list = guide_list if guide_list is not None else ALL_WEAK_GUIDE_IDS
        subs_lit = ",".join(str(s) for s in guide_list)
        expr = f"""(function()
            local m = _G.p12.sc_12111()
            for _, v in ipairs({{{subs_lit}}}) do
                m.mod_guide_list:append(v)
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_28837(self, sys_id_list: list[int] | None = None) -> bytes:
        """Encode sc_28837 (qworld unlock function list).

        QWorldAction Bind(28837) -> QWorldData:InitUnlockFunction sets
        unLockFunctionIdList_ = sys_id_list or {}. Without this push the list
        stays nil and GuideTool's CheckGuide chain dies on
        table.indexof(nil) ("attempt to get length of a nil value" reported
        under library/Oop/Functions) during LoginView.PlayOut.
        An empty list is fine: every function stays locked (newbie state).
        """
        sys_id_list = sys_id_list or []
        subs_lit = ",".join(str(s) for s in sys_id_list)
        expr = f"""(function()
            local m = _G.p28.sc_28837()
            for _, v in ipairs({{{subs_lit}}}) do
                m.sys_id_list:append(v)
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_32109(self, result: int = 0) -> bytes:
        """Encode sc_32109 (home scene setting response).

        The client's home-scene init (inside the 10201 callback chain) sends
        cs_32108 with poster_background_id=0; lua-protobuf omits the zero
        scalar so the wire pb is empty and C# Pack drops the whole request,
        leaving waitCallbacks_["32109_1"] dangling (20s timeout). Pushed by
        the server with index=1 on the same stream batch instead.
        """
        expr = f"""(function()
            local m = _G.p32.sc_32109()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_54031(self, result: int = 0) -> bytes:
        """Encode sc_54031 (enter battle response).

        Guide 501 step 50101 (tutorial battle) makes the client send
        cs_54030 whose pb is empty on the wire (C# Pack drops empty
        messages), so sc_54031 must be pushed by the server. Sent with
        index=1 so it matches the client's first indexed waitCallback key
        "54031_1".
        """
        expr = f"""(function()
            local m = _G.p54.sc_54031()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_54007(self, result: int = 0, battle_id: int = 1,
                        ip: str = "127.0.0.1", port: str = "5001") -> bytes:
        """Encode sc_54007 (battle start push).

        BattleController.LaunchBattle (battlecontroller_decomp.lua) sends
        cs_54030 then, in the sc_54031 success callback, registers
        RegistPushWaiting(54007, ...). BattleFieldAction Bind(54007) checks
        isSuccess(battle_start.result), prints "战斗开始", stores
        SetServerBattleParams(battle_id, ip, port) and calls StartBattle.
        NOT wired into the login stream: the waiting entry only exists while
        a battle launch is in flight (guides are skipped via sc_12011), so
        an unsolicited push would find no callback.
        Note: battle_server_port is a string field in p54_pb.
        """
        expr = f"""(function()
            local m = _G.p54.sc_54007()
            m.battle_start.result = {result}
            m.battle_start.battle_id = {battle_id}
            m.battle_start.battle_server_ip = "{ip}"
            m.battle_start.battle_server_port = "{port}"
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_59001(self, is_completed: int = 1) -> bytes:
        """Encode sc_59001 (newbie activity data init).

        ActivityNewbieAction binds 59001 and ActivityNewbieData:InitData uses
        it to mark the current version open. is_completed > 1 makes
        IsFinishAllActivity return true, preventing the main-home view from
        dereferencing missing NoobVersionCfg entries.
        """
        expr = f"""(function()
            local m = _G.p59.sc_59001()
            m.is_completed = {is_completed}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_14035(self, result: int = 0) -> bytes:
        """编码皮肤选择响应；请求索引由服务端正常回送。"""
        expr = f"""(function()
            local m = _G.p14.sc_14035()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_32055(self, result: int = 0) -> bytes:
        """编码看板角色触摸响应，包括客户端发送的空请求。"""
        expr = f"""(function()
            local m = _G.p32.sc_32055()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_32009(self, poster_bg_id: int = 6000, poster_girl: int = 1084) -> bytes:
        """初始化玩家名片与大厅场景，使用客户端配置中的默认名片背景。"""
        expr = f"""(function()
            local m = _G.p32.sc_32009()
            m.sign = 'DevServer'
            m.poster_girl = {poster_girl}
            m.poster_background_id = {poster_bg_id}
            m.icon = 2110841
            m.icon_frame = 2001
            m.sticker_background = 4002
            m.likes = 0
            m.information_background_id = 8001
            m.chat_bubble = 9001
            m.table_setting.entry_time = 0
            m.table_setting.switch_frequency = 0
            m.table_setting.pattern_scope = 0
            m.table_setting.pattern_id = 0
            local bg1 = m.poster_background_list:add()
            bg1.id = 6000
            bg1.lasted_time = 0
            local bg2 = m.poster_background_list:add()
            bg2.id = 6100
            bg2.lasted_time = 0
            local card_bg = m.information_background_list:add()
            card_bg.id = 8001
            card_bg.lasted_time = 0
            -- random_info is mandatory: PlayerCardInit (the 32009 handler) does
            -- ipairs(slot0.random_info) BEFORE HomeSceneSettingData:InitData.
            -- With the field absent, ipairs(nil) throws, InitData never runs,
            -- curSceneID_ stays 0, and later GetCurScene -> GetSceneID indexes
            -- HomeSceneSettingCfg[0] (nil) while computing the home scene name
            -- inside SetShouldLoadSceneName -> the "Levels/home" scene never
            -- loads (black home screen, UI still clickable).
            local ri2 = m.random_info:add()
            ri2.random_type = 2
            ri2.random_model = 0
            ri2.show_hero_dressing_scene = 0
            ri2.routine_hero_dressing_scene = 0
            local ri1 = m.random_info:add()
            ri1.random_type = 1
            ri1.random_model = 0
            ri1.show_hero_dressing_scene = 0
            ri1.routine_hero_dressing_scene = 0
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_12009(self, user_level: int = 80) -> bytes:
        """Encode sc_12009 (user level init)."""
        expr = f"""(function()
            local m = _G.p12.sc_12009()
            m.user_level = {user_level}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_23009(self, nick: str = "Enigfrank-Crack", total_exp: int = 70000,
                        hero_num: int = 1, plot_progress: int = 1) -> bytes:
        """Encode sc_23009 (player info init)."""
        expr = f"""(function()
            local m = _G.p23.sc_23009()
            m.nick = "{nick}"
            m.total_exp = {total_exp}
            m.hero_num = {hero_num}
            m.plot_progress = {plot_progress}
            m.is_changed_nick = 0
            m.system_change_nick_times = 0
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_15009(self, balances: dict[int, int] | None = None) -> bytes:
        """按 ItemCfg 分类下发全部原生货币，材料代币通过 17009 下发。"""
        balances = build_currency_balances() if balances is None else balances
        pairs = [(cid, balances[cid]) for cid in NATIVE_CURRENCY_IDS]
        spec = ",".join(f"{{{cid},{num}}}" for cid, num in pairs)
        expr = f"""(function()
            local m = _G.p15.sc_15009()
            m.last_fatigue_recover_time = os.time()
            local spec = {{{spec}}}
            for _, pair in ipairs(spec) do
                local c = m.currency_list:add()
                c.id = pair[1]
                c.num = pair[2]
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_14009(self, heroes: list[dict] | None = None) -> bytes:
        """Encode sc_14009 (hero info list init)."""
        if heroes is None:
            heroes = [{
                "id": 1084,
                "level": 80,
                "star": 100,
                "break_level": 6,
                "skin_id": 1084
            }]
        entries = []
        for hero in heroes:
            scalars = ",".join(f"{key}={int(value)}" for key, value in hero.items()
                               if isinstance(value, int))
            lists = ",".join(f"{key}={{{','.join(str(int(v)) for v in value)}}}"
                             for key, value in hero.items() if isinstance(value, list))
            entries.append("{" + scalars + ("," + lists if lists else "") + "}")
        list_lit = ";".join(entries)
        loadouts = ",".join(
            f"[{hid}]={{{','.join('{' + ','.join(str(skill) for skill in slot) + '}' for slot in warp)}}}"
            for hid, (_, warp, _) in HERO_LOADOUTS.items()
        )
        expr = f"""(function()
            local m = _G.p14.sc_14009()
            local loadouts = {{{loadouts}}}
            for _, info in ipairs({{{list_lit}}}) do
                local h = m.hero_info_list:add()
                h.unlock = info.unlock or 1
                h.clear_times = info.clear_times or 0
                h.weapon_module_assignment = (info.module_level or 0) > 0 and 1 or 0
                local bi = h.hero_base_info
                bi.id, bi.level, bi.star = info.id, info.level, info.star
                bi.exp = require('GameLevelSetting')[info.level].hero_lv_exp_sum
                bi.using_skin, bi.battle_using_skin = info.skin_id, info.battle_skin_id or info.skin_id
                bi.break_level = info.break_level
                bi.weapon_module_level = info.module_level or 0
                bi.weapon.exp = info.weapon_exp or 0
                bi.weapon.breakthrough = info.weapon_break or 0
                if info.servant_id then bi.weapon.servant_uid = info.servant_uid or info.id end
                for _, id in ipairs(info.skills or {{}}) do
                    local skill = bi.skill:add()
                    skill.skill_id, skill.skill_level = id, info.skill_level
                end
                for index = 1, 5 do
                    local attr = bi.skill_intensify_attribute_list:add()
                    attr.index, attr.level = index, info.skill_attr_level or 0
                end
                for _, id in ipairs(info.astrolabes or {{}}) do bi.unlock_astrolabe:append(id) end
                for _, id in ipairs(info.using_astrolabes or {{}}) do bi.using_astrolabe:append(id) end
                if info.equip_prefabs and #info.equip_prefabs > 0 then
                    for pos, skills in ipairs(loadouts[info.id]) do
                        local warp = bi.exclusive_skill_list:add()
                        warp.slot_id, warp.talent_points = pos, 6
                        for _, id in ipairs(skills) do
                            local skill = warp.skill_list:add()
                            skill.skill_id, skill.skill_level = id, 3
                        end
                    end
                end
                for pos = 1, 6 do
                    local equip = h.equip:add()
                    equip.pos, equip.equip_id = pos, info.equip_ids and info.equip_ids[pos] or 0
                end
                local tr = h.trust
                tr.level, tr.exp, tr.mood = info.trust_level or 1, 0, 1
                if info.trust_level == 5 then
                    local cfg = require('HeroRelationNetCfg')
                    for _, id in ipairs(cfg.get_id_list_by_hero_id[info.id] or {{}}) do
                        local tier = tr.relation.tier_list:add()
                        tier.tier = cfg[id].index
                        for index = 1, #cfg[id].relation_upgrade_group do
                            tier.upgrade_complete_list:append(index)
                        end
                    end
                else
                    local tier = tr.relation.tier_list:add()
                    tier.tier = 1
                end
                if #tr.relation.tier_list == 0 then
                    local tier = tr.relation.tier_list:add()
                    tier.tier = 1
                end
                for _, id in ipairs(info.skins or {{info.skin_id}}) do
                    local skin = h.unlocked_skin:add()
                    skin.skin_id, skin.time = id, 0
                end
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_13009(self, heroes: list[dict] | None = None) -> bytes:
        """为满养成角色初始化推荐刻印，升至配置上限并赋予角色专属属性。"""
        entries = []
        for hero in heroes or []:
            _, _, enchants = HERO_LOADOUTS[hero["id"]]
            for uid, prefab in zip(hero["equip_ids"], hero["equip_prefabs"]):
                skills = ",".join(str(skill) for skill in enchants)
                entries.append(f"{{{uid},{prefab},{hero['id']},{{{skills}}}}}")
        spec = ",".join(entries)
        expr = f"""(function()
            local m = _G.p13.sc_13009()
            m.is_init = 1
            for _, info in ipairs({{{spec}}}) do
                local cfg = require('EquipCfg')[info[2]] or require('EquipCfg2')[info[2]]
                local level = cfg.max_level[#cfg.max_level]
                local e = m.equip_list:add()
                e.equip_id, e.prefab_id, e.hero_id = info[1], info[2], info[3]
                e.exp = require('EquipExpCfg')[level]['exp_sum_' .. cfg.starlevel]
                e.is_lock, e.now_break_level, e.race = true, cfg.break_times_max, info[3]
                for slot = 1, cfg.slot_num do
                    local enchant = e.enchant_slot_list:add()
                    enchant.id = slot
                    for index = 1, 2 do
                        local skill = info[4][(slot - 1) * 2 + index]
                        if skill then
                            local effect = enchant.effect_list:add()
                            effect.id, effect.level = skill, 1
                        end
                    end
                end
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_17009(self, balances: dict[int, int] | None = None) -> bytes:
        """初始化 CurrencyIdMapCfg 中的全部材料代币，永久有效。"""
        balances = build_currency_balances() if balances is None else balances
        spec = ",".join(f"{{{cid},{balances[cid]}}}" for cid in MATERIAL_TOKEN_IDS)
        expr = f"""(function()
            local m = _G.p17.sc_17009()
            for _, pair in ipairs({{{spec}}}) do
                local item = m.material_list:add()
                item.id = pair[1]
                item.num = pair[2]
                item.time_valid = 0
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_46011(self, heroes: list[dict] | None = None) -> bytes:
        """初始化角色装备的专属钥从，与权钥的 servant_uid 对齐。"""
        entries = ",".join(f"{{{h['id']},{h['servant_id']},{h['servant_stage']}}}"
                           for h in (heroes or []) if h.get("servant_id"))
        expr = f"""(function()
            local m = _G.p46.sc_46011()
            for _, info in ipairs({{{entries}}}) do
                local servant = m.servant_list:add()
                servant.uid, servant.id, servant.stage = info[1], info[2], info[3]
                servant.is_locked = 1
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_20003(self, shop_id: int, goods: list[dict]) -> bytes:
        """下发单店铺动态商品定义，必须先于 20009 的商品库存发送。"""
        entries = ",".join("{" + ",".join(f"{key}={int(value)}" for key, value in item.items()) + "}"
                           for item in goods)
        expr = f"""(function()
            local m = _G.p20.sc_20003()
            m.shop_item_cfg_list.shop_id = {shop_id}
            for index, info in ipairs({{{entries}}}) do
                local g = m.shop_item_cfg_list.goods_list:add()
                for _, f in ipairs(_G.p20.GOODS_CFG.fields) do
                    if f.label == 2 then g[f.name] = 0 end
                end
                g.goods_id, g.description = info.goods_id, info.description
                g.shop_sort, g.cost_type = index, 0
                g.cost_id, g.cost = info.cost_id, info.cost
                g.cheap_cost_id, g.cheap_cost = info.cost_id, info.cost
                g.limit_num, g.limit_display = -1, 1
                g.refresh_cycle = 0
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_28001(self) -> bytes:
        """Encode sc_28001 (task list init)."""
        expr = """(function()
            local m = _G.p28.sc_28001()
            m.send_type = 0
            m.newbie_phase = 0
            m.assignment_phase = 0
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_16015(self) -> bytes:
        """Encode sc_16015 (draw pool init)."""
        expr = """(function()
            local m = _G.p16.sc_16015()
            m.today_draw_times = 0
            m.newbie_choose_draw_flag = false
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_19029(self) -> bytes:
        """Encode sc_19029 (friends list init)."""
        expr = """(function()
            local m = _G.p19.sc_19029()
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_20009(self, shop_goods: dict[int, list[int]] | None = None) -> bytes:
        """Encode sc_20009 (shop list init).

        shop_goods maps shop_id -> goods_id list. shop_info fields: shop_id=1,
        refresh_times=2, goods_list=3, is_need_tag=4 (required bool, must be
        an explicit Lua boolean - numeric 0 or table fails the tolua type
        checker). goods_info: goods_id=1, buy_times=2, next_refresh_timestamp=3
        (all required - zero values MUST be set explicitly or SerializeToString
        rejects the message)."""
        if not shop_goods:
            shop_goods = {2: []}
        chunks = []
        for sid in sorted(shop_goods):
            goods = ",".join(f"{{{gid},0,0}}" for gid in shop_goods[sid])
            chunks.append(f"{{{sid},0,{{{goods}}}}}")
        spec = ",".join(chunks)
        expr = f"""(function()
            local m = _G.p20.sc_20009()
            local spec = {{{spec}}}
            for _, shop in ipairs(spec) do
                local s = m.shop_item_list:add()
                s.shop_id = shop[1]
                s.refresh_times = shop[2]
                s.is_need_tag = false
                for _, g in ipairs(shop[3]) do
                    local gi = s.goods_list:add()
                    gi.goods_id = g[1]
                    gi.buy_times = g[2]
                    gi.next_refresh_timestamp = g[3]
                end
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_20005(self, shop_id: int, goods_ids: list[int]) -> bytes:
        """Encode sc_20005 (single-shop change push).

        changed_shop_info wraps one shop_info: shop_id=1, refresh_times=2,
        goods_list=3, is_need_tag=4 (required bool).
        """
        goods = ",".join(f"{{{gid},0,0}}" for gid in goods_ids)
        expr = f"""(function()
            local m = _G.p20.sc_20005()
            local s = m.changed_shop_info
            s.shop_id = {shop_id}
            s.refresh_times = 0
            s.is_need_tag = false
            for _, g in ipairs({{{goods}}}) do
                local gi = s.goods_list:add()
                gi.goods_id = g[1]
                gi.buy_times = g[2]
                gi.next_refresh_timestamp = g[3]
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)

    def encode_sc_30001(self) -> bytes:
        """Encode sc_30001 (mail list init)."""
        expr = """(function()
            local m = _G.p30.sc_30001()
            m.unread_number = 0
            m.total_number = 0
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(expr)


    def encode_sc_19031(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p19.sc_19031()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_27011(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p27.sc_27011()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_27005(self, room_id: int = 1) -> bytes:
        script = f"""(function()
            local m = _G.p27.sc_27005()
            m.room_id = {room_id}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_27009(self, mute_reason: str = "", ban_timestamp: int = 0) -> bytes:
        r_hex = str(mute_reason or "").encode("utf-8").hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local m = _G.p27.sc_27009()
            m.mute_reason = from_hex('{r_hex}')
            m.ban_timestamp = {int(ban_timestamp)}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_27015(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p27.sc_27015()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_27101(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p27.sc_27101()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_12037(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p12.sc_12037()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_19035(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p19.sc_19035()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_19001(self) -> bytes:
        script = """(function()
            local m = _G.p19.sc_19001()
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_12039(self, custom_stickers: list[int] | None = None, unlocked_stickers: list[int] | None = None) -> bytes:
        if custom_stickers is None:
            custom_stickers = list(range(1, 17))
        if unlocked_stickers is None:
            unlocked_stickers = list(range(1, 381))
        
        c_str = ", ".join(str(x) for x in custom_stickers)
        u_str = ", ".join(str(x) for x in unlocked_stickers)
        script = f"""(function()
            local m = _G.p12.sc_12039()
            for _, id in ipairs({{{c_str}}}) do
                m.emoticon_id_list:append(id)
            end
            for _, id in ipairs({{{u_str}}}) do
                m.unlocked_emoji_list:append(id)
            end
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def encode_sc_27007(self, chat_msg_list: list[dict] | None = None) -> bytes:
        if not chat_msg_list:
            chat_msg_list = []
        lines = [
            "local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end",
            "local m = _G.p27.sc_27007()"
        ]
        for item in chat_msg_list:
            nick_h = str(item.get("nick", "User")).encode("utf-8").hex()
            content_h = str(item.get("content", "")).encode("utf-8").hex()
            loc_h = str(item.get("ip_location", "本地")).encode("utf-8").hex()
            lines.append(f"""
            do
                local item = m.chat_msg_list:add()
                item.room_id = {_safe_int(item.get('room_id'), 1)}
                local msg = item.msg
                msg.id = {_safe_int(item.get('uid'), 10001)}
                msg.user_profile_base.nick = from_hex('{nick_h}')
                msg.user_profile_base.icon = {_safe_int(item.get('icon'), 1084)}
                msg.user_profile_base.icon_frame = {_safe_int(item.get('icon_frame'), 2001)}
                msg.type = {_safe_int(item.get('type'), 1)}
                msg.content = from_hex('{content_h}')
                msg.timestamp = {_safe_int(item.get('timestamp'), 0)}
                msg.msg_id = {_safe_int(item.get('msg_id'), 1)}
                msg.ip_location = from_hex('{loc_h}')
                msg.chat_bubble = {_safe_int(item.get('chat_bubble'), 9001) or 9001}
            end
            """)
        lines.append("return m:SerializeToString()")
        joined_lines = "\n".join(lines)
        return self.run_lua_expr(f"(function()\n{joined_lines}\nend)()")

    def encode_sc_19039(self, friend_msg_list: list[dict] | None = None) -> bytes:
        if not friend_msg_list:
            friend_msg_list = []
        lines = [
            "local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end",
            "local m = _G.p19.sc_19039()"
        ]
        for item in friend_msg_list:
            nick_h = str(item.get("nick", "User")).encode("utf-8").hex()
            content_h = str(item.get("content", "")).encode("utf-8").hex()
            loc_h = str(item.get("ip_location", "本地")).encode("utf-8").hex()
            lines.append(f"""
            do
                local it = m.friend_msg_list:add()
                it.receive_uid = {_safe_int(item.get('receive_uid'), 0)}
                local b = it.chat_base_info
                b.id = {_safe_int(item.get('sender_uid', item.get('uid')), 10001)}
                b.type = {_safe_int(item.get('type'), 1)}
                b.content = from_hex('{content_h}')
                b.timestamp = {_safe_int(item.get('timestamp'), 0)}
                b.msg_id = {_safe_int(item.get('msg_id'), 1)}
                b.ip_location = from_hex('{loc_h}')
                b.chat_bubble = {_safe_int(item.get('chat_bubble'), 9001) or 9001}
                b.user_profile_base.nick = from_hex('{nick_h}')
                b.user_profile_base.icon = {_safe_int(item.get('icon'), 1084)}
                b.user_profile_base.icon_frame = {_safe_int(item.get('icon_frame'), 2001)}
            end
            """)
        lines.append("return m:SerializeToString()")
        joined_lines = "\n".join(lines)
        return self.run_lua_expr(f"(function()\n{joined_lines}\nend)()")

    def encode_sc_generic(self, cmd: int, result: int = 0) -> bytes:
        script = f"""(function()
            local cmd = {int(cmd)}
            local mod_num = math.floor(cmd / 1000)
            local mod_name = string.format("p%02d", mod_num)
            local ok, mod = pcall(require, mod_name .. '_pb')
            if not ok or not mod then
                mod_name = 'p' .. tostring(mod_num)
                ok, mod = pcall(require, mod_name .. '_pb')
            end
            if ok and mod and mod['sc_' .. tostring(cmd)] then
                local ok2, msg = pcall(mod['sc_' .. tostring(cmd)])
                if ok2 and msg then
                    pcall(function() msg.result = {int(result)} end)
                    local ok3, res = pcall(function() return msg:SerializeToString() end)
                    if ok3 and res then return res end
                end
            end
            return string.char(8, {int(result)})
        end)()"""
        res = self.run_lua_expr(script)
        return res if res else b"\x08\x00"

    def decode_cs_14034(self, payload: bytes) -> dict:
        """解析皮肤切换请求，交由账号存档验证归属和永久保存。"""
        expression = f"""(function()
            local m = _G.p14.cs_14034()
            local raw = ('{payload.hex()}'):gsub('..', function(c) return string.char(tonumber(c, 16)) end)
            m:ParseFromString(raw)
            return string.format('%d,%d', m.hero_id, m.skin_id)
        end)()"""
        hid, skin = self.run_lua_expr(expression).decode("ascii").split(",")
        return {"hero_id": int(hid), "skin_id": int(skin)}

    def decode_cs_27014(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local function to_hex(s) return (s:gsub('.', function(c) return string.format('%02x', string.byte(c)) end)) end
            local m = _G.p27.cs_27014()
            m:ParseFromString(from_hex('{hex_s}'))
            return tostring(m.type or 1) .. '|' .. to_hex(m.content or '')
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        parts = res.split('|', 1)
        m_type = int(parts[0]) if parts[0].isdigit() else 1
        content = bytes.fromhex(parts[1]).decode('utf-8', errors='replace') if len(parts) > 1 and parts[1] else ""
        return {"type": m_type, "content": content}

    def encode_sc_27013(self, result: int = 0) -> bytes:
        script = f"""(function()
            local m = _G.p27.sc_27013()
            m.result = {result}
            return m:SerializeToString()
        end)()"""
        return self.run_lua_expr(script)

    def decode_cs_27012(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local m = _G.p27.cs_27012()
            m:ParseFromString(from_hex('{hex_s}'))
            return tostring(m.operation or 1)
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        return {"operation": int(res) if res.isdigit() else 1}

    def decode_cs_19036(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local m = _G.p19.cs_19036()
            m:ParseFromString(from_hex('{hex_s}'))
            local ids = {{}}
            for i = 1, #m.msg_id_list do
                table.insert(ids, tostring(m.msg_id_list[i]))
            end
            return tostring(m.channel or 0) .. '|' .. table.concat(ids, ',')
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        parts = res.split("|", 1)
        channel = int(parts[0]) if parts[0].isdigit() else 0
        ids = [int(x) for x in parts[1].split(",") if x.strip().isdigit()] if len(parts) > 1 and parts[1] else []
        return {"channel": channel, "msg_id_list": ids}


    def decode_cs_27010(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local m = _G.p27.cs_27010()
            m:ParseFromString(from_hex('{hex_s}'))
            return tostring(m.room_id or 1)
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        return {"room_id": int(res) if res.isdigit() else 1}

    def decode_cs_27100(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local function to_hex(s) return (s:gsub('.', function(c) return string.format('%02x', string.byte(c)) end)) end
            local m = _G.p27.cs_27100()
            m:ParseFromString(from_hex('{hex_s}'))
            return to_hex(m.content or '')
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        content = bytes.fromhex(res).decode('utf-8', errors='replace') if res else ""
        return {"content": content}

    def decode_cs_12036(self, payload: bytes) -> list[int]:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local m = _G.p12.cs_12036()
            m:ParseFromString(from_hex('{hex_s}'))
            local t = {{}}
            for i = 1, #m.emoticon_id_list do
                table.insert(t, tostring(m.emoticon_id_list[i]))
            end
            return table.concat(t, ',')
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        if not res.strip():
            return []
        return [int(x) for x in res.split(',') if x.strip().isdigit()]

    def decode_cs_19030(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local m = _G.p19.cs_19030()
            m:ParseFromString(from_hex('{hex_s}'))
            return tostring(m.type or 1)
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        return {"type": int(res) if res.isdigit() else 1}

    def decode_cs_19034(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local function to_hex(s) return (s:gsub('.', function(c) return string.format('%02x', string.byte(c)) end)) end
            local m = _G.p19.cs_19034()
            m:ParseFromString(from_hex('{hex_s}'))
            return tostring(m.receive_uid or 0) .. '|' .. tostring(m.type or 1) .. '|' .. to_hex(m.content or '')
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        parts = res.split('|', 2)
        r_uid = int(parts[0]) if parts[0].isdigit() else 0
        m_type = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        content = bytes.fromhex(parts[2]).decode('utf-8', errors='replace') if len(parts) > 2 and parts[2] else ""
        return {"receive_uid": r_uid, "type": m_type, "content": content}

    def decode_cs_10038(self, payload: bytes) -> dict:
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local function to_hex(s) return (s:gsub('.', function(c) return string.format('%02x', string.byte(c)) end)) end
            local m = _G.p10.cs_10038()
            m:ParseFromString(from_hex('{hex_s}'))
            return tostring(m.channel_id or 0) .. '|' .. to_hex(m.account or '') .. '|' .. to_hex(m.token or '')
        end)()"""
        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')
        parts = res.split('|', 2)
        channel_id = int(parts[0]) if parts[0].isdigit() else 0
        account = bytes.fromhex(parts[1]).decode('utf-8', errors='replace') if len(parts) > 1 and parts[1] else ""
        token = bytes.fromhex(parts[2]).decode('utf-8', errors='replace') if len(parts) > 2 and parts[2] else ""
        return {"channel_id": channel_id, "account": account, "token": token}

    def decode_cs_10042(self, payload: bytes) -> dict:
        """解码 cs_10042,采用更健壮的方式处理可能损坏的 protobuf 数据"""
        # 尝试标准解码
        hex_s = payload.hex()
        script = f"""(function()
            local function from_hex(h) return (h:gsub('..', function(c) return string.char(tonumber(c, 16)) end)) end
            local function to_hex(s) return (s:gsub('.', function(c) return string.format('%02x', string.byte(c)) end)) end
            local m = _G.p10.cs_10042()
            local ok, err = pcall(function() m:ParseFromString(from_hex('{hex_s}')) end)
            if not ok then
                return 'ERROR|' .. tostring(err)
            end
            return tostring(m.user_id or 10001) .. '|' .. to_hex(m.account or '') .. '|' .. to_hex(m.gstoken or '')
        end)()"""

        res = self.run_lua_expr(script).decode('utf-8', errors='ignore')

        # 如果 Lua 解码失败,手动解析关键字段
        if res.startswith('ERROR'):
            print(f"[协议桥接] Lua 解码失败: {res}, 改用手动解析")
            return self._manual_decode_cs_10042(payload)

        parts = res.split('|', 2)
        u_id = int(parts[0]) if parts[0].isdigit() else 10001
        account = bytes.fromhex(parts[1]).decode('utf-8', errors='replace') if len(parts) > 1 and parts[1] else ""
        gstoken = bytes.fromhex(parts[2]).decode('utf-8', errors='replace') if len(parts) > 2 and parts[2] else ""
        return {"user_id": u_id, "account": account, "gstoken": gstoken}

    def _manual_decode_cs_10042(self, payload: bytes) -> dict:
        """手动解析 cs_10042 的关键字段,跳过损坏的部分"""
        result = {"user_id": 0, "account": "", "gstoken": ""}
        pos = 0

        while pos < len(payload):
            if pos >= len(payload):
                break

            tag = payload[pos]
            field_id = tag >> 3
            wire_type = tag & 0x07
            pos += 1

            # 跳过非法的 wire_type
            if wire_type > 5:
                print(f"[协议桥接] 无效的编码类型（wire_type）={wire_type}，位置={pos-1}，停止解析")
                break

            try:
                if wire_type == 0:  # varint
                    value = 0
                    shift = 0
                    while pos < len(payload):
                        b = payload[pos]
                        pos += 1
                        value |= (b & 0x7f) << shift
                        if not (b & 0x80):
                            break
                        shift += 7

                    # 当前客户端 field_id=4 是 user_id。
                    if field_id == 4:
                        result["user_id"] = value

                elif wire_type == 2:  # length-delimited
                    length = 0
                    shift = 0
                    while pos < len(payload):
                        b = payload[pos]
                        pos += 1
                        length |= (b & 0x7f) << shift
                        if not (b & 0x80):
                            break
                        shift += 7

                    # 检查长度是否合理
                    if length > len(payload) - pos:
                        print(f"[协议桥接] 字段 {field_id} 声明长度为 {length} 但仅剩 {len(payload)-pos} 字节")
                        break

                    data = payload[pos:pos+length]
                    pos += length

                    # 当前客户端 field_id=3 是 account，field_id=6 是 gstoken。
                    if field_id == 3:
                        result["account"] = data.decode('utf-8', errors='replace')
                    elif field_id == 6:
                        result["gstoken"] = data.decode('utf-8', errors='replace')

                elif wire_type == 5:  # 32-bit
                    pos += 4
                elif wire_type == 1:  # 64-bit
                    pos += 8

            except Exception as e:
                print(f"[协议桥接] 解析字段出错 {field_id}: {e}")
                break

        print(f"[协议桥接] 手动解析结果：用户 ID={result['user_id']}，账号={result['account'][:20]}...")
        return result

_BRIDGE = None
def get_bridge() -> ToluaBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = ToluaBridge()
    return _BRIDGE

if __name__ == "__main__":
    b = get_bridge()
    p_10039 = b.encode_sc_10039(timestamp=1700000000)
    print(f"sc_10039 ({len(p_10039)}字节): {p_10039.hex()}")
    assert p_10039.hex() == "080010011a093132372e302e302e3120892728914e32146465765f6d6f636b5f746f6b656e5f31323334353880e2cfaa064000"
    
    p_10043 = b.encode_sc_10043(timestamp=1700000000, register_timestamp=1700000000, verify_timestamp=1700000000)
    print(f"sc_10043 ({len(p_10043)}字节): {p_10043.hex()}")
    assert p_10043.hex() == "08001080e2cfaa061880e2cfaa062080e2cfaa062a0d6d6f636b5f7569645f7369676e"

    print("正在测试聊天、通用响应与贴纸方法……")
    assert b.encode_sc_19031(0).hex() == "0800"
    assert b.encode_sc_27011(0).hex() == "0800"
    assert b.encode_sc_27005(1).hex() == "0801"
    assert b.encode_sc_27015(0).hex() == "0800"
    assert b.encode_sc_27101(0).hex() == "0800"
    assert b.encode_sc_12037(0).hex() == "0800"
    assert b.encode_sc_19035(0).hex() == "0800"
    assert b.encode_sc_19001() == b""
    assert len(b.encode_sc_12039([1, 2], [1, 2, 3])) > 0
    
    m_27007 = b.encode_sc_27007([{"uid": 10001, "nick": "Player", "icon": 1084, "icon_frame": 2001, "type": 1, "content": "Hello \"world\" \x27test\x27", "timestamp": 1700000000, "msg_id": 1, "room_id": 1}])
    assert len(m_27007) > 0
    
    m_19039 = b.encode_sc_19039([{"receive_uid": 10002, "sender_uid": 10001, "nick": "Player", "icon": 1084, "icon_frame": 2001, "type": 1, "content": "Priv \"test\"", "timestamp": 1700000000, "msg_id": 1}])
    assert len(m_19039) > 0

    assert b.encode_sc_generic(19031, 0).hex() == "0800"
    assert b.encode_sc_generic(99999, 0).hex() == "0800"

    print("ToluaBridge 全部测试通过！")
