"""验证入口修复所依赖的收包边界、客户端配置与实际 protobuf 数据。"""

import asyncio
import json
import struct
from unittest.mock import patch

import server
from activity_data import RESOURCE_ACTIVITIES, RESOURCE_ACTIVITY_THEME, build_available_activities
from currency_data import CURRENCY_DEFINITIONS, NATIVE_CURRENCY_IDS, MATERIAL_TOKEN_IDS, build_currency_balances
from proto_bridge import get_bridge
from push_data import SHOP_GOODS_NOREFRESH


class MemoryWriter:
    """在内存中记录网络响应，避免测试监听端口或修改存档。"""

    def __init__(self):
        """初始化输出缓冲区和关闭状态。"""
        self.output = bytearray()
        self.closed = False

    def get_extra_info(self, _):
        """提供测试连接地址。"""
        return ("test", 0)

    def write(self, data):
        """记录服务器发送的完整数据。"""
        self.output.extend(data)

    async def drain(self):
        """模拟异步写入完成。"""
        pass

    def is_closing(self):
        """返回连接关闭状态。"""
        return self.closed

    def close(self):
        """标记测试连接已关闭。"""
        self.closed = True

    async def wait_closed(self):
        """模拟连接关闭完成。"""
        pass


async def test_request_framing():
    """将长请求、空请求和心跳拆分及合并输入，验证 uint32 长度不会串包。"""
    reader = asyncio.StreamReader()
    writer = MemoryWriter()
    requests = [(10042, 1, b"x" * 442 + b"\x08\x01"), (20016, 2, b""), (10050, 0, b"\x08\x01")]
    frames = []
    for cmd, index, body in requests:
        payload = struct.pack("<BIHH", 8, cmd, index, 0) + body
        frames.append(struct.pack("<I", len(payload)) + payload)
    received = []

    def respond(opcode, flag, rpc_id, body, **_):
        """检查传输层输出原始请求体，并回送具有同一索引的响应。"""
        assert (opcode, flag, rpc_id) == (2048, 0, 0)
        cmd, index, ack = struct.unpack_from("<IHH", body)
        assert ack == 0
        received.append((cmd, index, body[8:]))
        return server.pack_ystcp(cmd + 1, index=index)

    with patch.object(server, "handle_tcp_message", side_effect=respond):
        task = asyncio.create_task(server.handle_tcp_client(reader, writer))
        reader.feed_data(frames[0][:3])
        await asyncio.sleep(0)
        reader.feed_data(frames[0][3:100])
        await asyncio.sleep(0)
        reader.feed_data(frames[0][100:] + frames[1] + frames[2])
        reader.feed_eof()
        await task
    assert received == requests
    assert writer.output == b"".join(server.pack_ystcp(cmd + 1, index=index) for cmd, index, _ in requests)
    assert writer not in server.CLIENT_SESSIONS


def decode_message(module: str, command: int, payload: bytes, checks: str):
    """使用客户端 protobuf 解析真实编码结果，并执行配置一致性断言。"""
    result = get_bridge().run_lua_expr(f"""(function()
        local m = require('{module}').sc_{command}()
        local raw = ('{payload.hex()}'):gsub('..', function(c) return string.char(tonumber(c, 16)) end)
        m:ParseFromString(raw)
        {checks}
        return 'ok'
    end)()""")
    assert result == b"ok"


def test_sdk_account_info():
    """定期 SDK 查询须与本地成年账号登录信息一致，不能返回空对象。"""
    body, _ = server.route_http_response("POST /sdk-api/auth/user/indulge/getInfo HTTP/1.1")
    response = json.loads(body)
    assert response["code"] == 0 and response["data"]["adult"] is True
    assert response["data"]["age"] >= 18 and response["data"]["remainingTime"] > 0


def test_initialization_data():
    """验证货币分类完整、存档余额保留、名片有效、商店完整及当前活动配置。"""
    bridge = get_bridge()
    balances = build_currency_balances({"diamond": 888888, "gold": 12345, "stamina": 200, "currencies": {"53103": 123}})
    assert balances[1] == 888888 and balances[2] == 12345 and balances[4] == 200
    assert balances[53103] == 123 and balances[31] == 99999
    assert len(NATIVE_CURRENCY_IDS) == 196 and len(MATERIAL_TOKEN_IDS) == 108
    definitions = ",".join(f"[{cid}]={kind}" for cid, (kind, _) in CURRENCY_DEFINITIONS.items())
    assert bridge.run_lua_expr(f"""(function()
        local cfg = require('ItemCfg')
        local types = {{{definitions}}}
        for id, kind in pairs(types) do
            if kind == 0 then assert(cfg[id] == nil) else assert(cfg[id].type == kind) end
        end
        for _, id in ipairs(cfg.get_id_list_by_type[1]) do assert(types[id] == 1) end
        for _, item in pairs(require('CurrencyIdMapCfg')) do
            if type(item) == 'table' and item.item_id then assert(types[item.item_id] ~= nil) end
        end
        return 'ok'
    end)()""") == b"ok"
    decode_message("p15_pb", 15009, bridge.encode_sc_15009(balances), """
        assert(#m.currency_list == 196)
        local ids = {}
        for _, item in ipairs(m.currency_list) do
            assert(require('ItemCfg')[item.id].type == 1 and not ids[item.id])
            ids[item.id] = item.num
        end
        assert(ids[1] == 888888 and ids[2] == 12345 and ids[4] == 200)
    """)
    decode_message("p17_pb", 17009, bridge.encode_sc_17009(balances), """
        assert(#m.material_list == 108)
        for _, item in ipairs(m.material_list) do assert(require('ItemCfg')[item.id].type == 6) end
    """)
    decode_message("p32_pb", 32009, bridge.encode_sc_32009(), """
        assert(m.information_background_id == require('GameSetting').profile_business_card_default.value[1])
        assert(require('ProfileDecorateItemCfg')[m.information_background_id] ~= nil)
        assert(m.information_background_list[1].id == m.information_background_id)
    """)
    shop_payload = bridge.encode_sc_20009(SHOP_GOODS_NOREFRESH)
    assert len(shop_payload) + 9 <= 65535
    total_goods = sum(len(goods) for goods in SHOP_GOODS_NOREFRESH.values())
    decode_message("p20_pb", 20009, shop_payload, f"""
        assert(#m.shop_item_list == {len(SHOP_GOODS_NOREFRESH)})
        local count = 0
        for _, shop in ipairs(m.shop_item_list) do count = count + #shop.goods_list end
        assert(count == {total_goods})
    """)
    decode_message("p11_pb", 11001, bridge.encode_sc_11001(), f"""
        assert(#m.activity_list == {len(build_available_activities())})
        local ids = {{}}
        for _, activity in ipairs(m.activity_list) do
            local cfg = require('ActivityCfg')[activity.activity_id]
            assert(cfg.activity_theme == activity.theme)
            if activity.state == 1 then assert(activity.stop_time > os.time())
            else assert(activity.state == 0 and activity.stop_time < os.time()) end
            assert(cfg.activity_template == activity.template)
            ids[activity.activity_id] = true
        end
        for _, id in ipairs(require('ActivityCfg').all) do
            if require('ActivityCfg')[id].activity_theme == {RESOURCE_ACTIVITY_THEME} then assert(ids[id]) end
        end
        for _, activity in ipairs(m.activity_list) do
            if activity.state == 1 then
                for _, id in ipairs(activity.sub_activity_id_list) do assert(ids[id]) end
            end
        end
        assert(ids[4412001] and ids[4410001])
        local cfg = require('ChapterClientCfg')
        for _, id in ipairs(cfg.get_id_list_by_toggle[8]) do
            local parent = require('ActivityCfg').get_id_list_by_sub_activity_list[cfg[id].activity_id][1]
            assert(ids[parent])
            assert(ids[cfg[id].activity_id])
        end
    """)


if __name__ == "__main__":
    asyncio.run(test_request_framing())
    test_sdk_account_info()
    test_initialization_data()
    print("入口分帧与初始化回归测试通过。")
