"""核对 Developer 养成数据、完整补给定义和大包传输。"""

import struct
from types import SimpleNamespace
from unittest.mock import patch

import server
from hero_data import build_max_heroes
from proto_bridge import get_bridge
from push_data import SHOP_GOODS_NOREFRESH
from tests.test_entry_flow import decode_message
from supply_data import SUPPLY_DEFINITIONS, build_supply_goods


def test_max_heroes():
    """按真实客户端配置验证可玩角色、皮肤、技能、神格与刻印上限。"""
    bridge = get_bridge()
    heroes = build_max_heroes([{"id": 1084, "skin_id": 108403}])
    assert next(h for h in heroes if h["id"] == 1084)["skin_id"] == 108403
    assert len(heroes) == 84 and sum(len(h["skins"]) for h in heroes) == 185
    decode_message("p14_pb", 14009, bridge.encode_sc_14009(heroes), """
        local cfg = require('HeroCfg')
        assert(#m.hero_info_list == #cfg.get_id_list_by_private[0])
        local owned = {}
        for _, h in ipairs(m.hero_info_list) do
            local b = h.hero_base_info
            assert(not owned[b.id] and cfg[b.id].private == 0 and h.unlock == 1)
            owned[b.id] = true
            assert(b.level == require('GameSetting').hero_level_max.value[1])
            assert(b.star == 600 and b.break_level == 8)
            assert(require('HeroBreakCfg')[cfg[b.id].race * 10 + b.break_level].max_level == b.level)
            assert(#b.skill == #cfg[b.id].skills)
            for i, skill in ipairs(b.skill) do
                assert(skill.skill_id == cfg[b.id].skills[i])
                assert(skill.skill_level == require('GameSetting').hero_skill_level_max.value[1])
            end
            assert(#b.skill_intensify_attribute_list == 5)
            for _, skill in ipairs(b.skill_intensify_attribute_list) do
                assert(skill.level == require('GameSetting').hero_skill_attr_level_max.value[1])
            end
            assert(#h.unlocked_skin == #require('SkinCfg').get_id_list_by_hero[b.id])
            for _, skin in ipairs(h.unlocked_skin) do
                assert(require('SkinCfg')[skin.skin_id].hero == b.id and skin.time == 0)
            end
            assert(b.weapon.exp == require('GameLevelSetting')[60].weapon_lv_exp_sum)
            assert(b.weapon.breakthrough == 4 and b.weapon.servant_uid == b.id)
            assert(#h.equip == 6 and #b.exclusive_skill_list == 6 and h.trust.level == 5)
            for _, warp in ipairs(b.exclusive_skill_list) do
                local levels = 0
                for _, skill in ipairs(warp.skill_list) do levels = levels + skill.skill_level end
                assert(warp.talent_points == 6 and levels <= 6)
            end
        end
        for _, id in ipairs(cfg.get_id_list_by_private[0]) do assert(owned[id]) end
    """)
    decode_message("p13_pb", 13009, bridge.encode_sc_13009(heroes), """
        assert(#m.equip_list == 84 * 6)
        for _, item in ipairs(m.equip_list) do
            local cfg = require('EquipCfg')[item.prefab_id] or require('EquipCfg2')[item.prefab_id]
            assert(cfg.pos == item.equip_id % 10 and item.hero_id == math.floor(item.equip_id / 10))
            assert(item.now_break_level == cfg.break_times_max and item.race == item.hero_id)
            assert(item.exp == require('EquipExpCfg')[cfg.max_level[#cfg.max_level]]['exp_sum_' .. cfg.starlevel])
        end
    """)
    decode_message("p46_pb", 46011, bridge.encode_sc_46011(heroes), """
        assert(#m.servant_list == 84)
        for _, item in ipairs(m.servant_list) do
            local cfg = require('WeaponServantCfg')[item.id]
            assert(require('WeaponEffectCfg')[cfg.effect[1]].spec_char[1] == tonumber(item.uid))
            assert(item.stage == 5 and item.is_locked == 1)
        end
    """)


def test_supply_and_compression():
    """验证每条补给描述均有动态配置及库存，大包能无损压缩封装。"""
    bridge = get_bridge()
    supplies = build_supply_goods()
    seen = set()
    shops = dict(SHOP_GOODS_NOREFRESH)
    for sid, goods in supplies.items():
        for item in goods:
            assert item["description"] not in seen
            seen.add(item["description"])
        decode_message("p20_pb", 20003, bridge.encode_sc_20003(sid, goods), f"""
            local shop = m.shop_item_cfg_list
            assert(shop.shop_id == {sid} and #shop.goods_list == {len(goods)})
            for _, item in ipairs(shop.goods_list) do
                assert(require('RechargeShopDescriptionCfg')[item.description] ~= nil)
                assert(item.goods_id == 900000000 + item.description)
            end
        """)
        shops[sid] = shops.get(sid, []) + [item["goods_id"] for item in goods]
    assert seen == set(SUPPLY_DEFINITIONS) and len(seen) == 884
    known = ",".join(f"[{id}]=true" for id in seen)
    assert bridge.run_lua_expr(f"""(function()
        local known = {{{known}}}
        for _, id in ipairs(require('RechargeShopDescriptionCfg').all) do assert(known[id]) end
        return 'ok'
    end)()""") == b"ok"
    raw = bridge.encode_sc_20009(shops)
    assert len(raw) + 9 > 65535
    packet = server.pack_ystcp(20009, raw, index=7, server_index=7)
    size = struct.unpack_from(">H", packet)[0]
    assert size <= 65535 and len(packet) == size + 2
    flag, cmd, index, ack, decoded = server.unpack_ystcp(packet[2:])
    assert (flag, cmd, index, ack, decoded) == (1, 20009, 7, 7, raw)


def test_skin_persistence():
    """验证有效皮肤被保存，其他角色的皮肤不会写入存档。"""
    user = {"heroes": build_max_heroes(), "token": "isolated-test-token"}
    saved = []
    manager = SimpleNamespace(save_user=lambda item: saved.append(item), get_user_by_uid=lambda _: user)
    session = SimpleNamespace(user_data=user, user_id=10001, token=user['token'])
    for skin, valid in ((108403, True), (1011, False)):
        request = b"\x08" + server.encode_varint(1084) + b"\x10" + server.encode_varint(skin)
        with patch.object(server, "get_user_manager", return_value=manager):
            response = server.handle_tcp_message(2048, 0, 0, struct.pack("<IHH", 14034, 7, 0) + request, session=session)
        body = server.unpack_ystcp(response[2:])[4]
        decode_message("p14_pb", 14035, body, f"assert(m.result == {0 if valid else 1})")
    assert len(saved) == 1 and next(h for h in user["heroes"] if h["id"] == 1084)["skin_id"] == 108403


if __name__ == "__main__":
    test_max_heroes()
    test_supply_and_compression()
    test_skin_persistence()
    print("Developer 角色、补给目录和压缩帧验证通过。")
