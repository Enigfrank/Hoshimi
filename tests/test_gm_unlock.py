"""隔离账号验证满配角色 GM 指令、实际装备引用、在线推送及重启恢复。"""

from copy import deepcopy
import struct

import server
import user_storage
from account_unlocks import unlock_catalog
from currency_data import build_currency_balances
from gameplay_protocol import decode_message
from hero_data import HERO_DEFINITIONS, HERO_LOADOUTS
from tests.test_entry_flow import MemoryWriter
from tests.test_gameplay_persistence import request
from tests.test_gm_features import admin, isolated_accounts


def read_pushes(writer):
    """解析真实在线连接收到的协议帧，验证完整装备库存与角色一起下发。"""
    raw, pushes = bytes(writer.output), {}
    while raw:
        size = struct.unpack_from('>H', raw)[0]
        _, command, _, _, body = server.unpack_ystcp(raw[2:2 + size])
        pushes[command] = decode_message(command, body, 'sc')
        raw = raw[2 + size:]
    writer.output.clear()
    return pushes


def assert_max_characters(pushes):
    """核对满配角色装备、完整皮肤，以及客户端配置的全部场景和视角。"""
    heroes = pushes[14009]['hero_info_list']
    equipment = {e['equip_id']: e for e in pushes[13009]['equip_list']}
    servants = {s['uid']: s for s in pushes[46011]['servant_list']}
    skins = {}
    for row in unlock_catalog()['skins']:
        skins.setdefault(row['hero'], set()).add(row['id'])
    assert set(unlock_catalog()['scenes']) <= {s['id'] for s in pushes[32009]['poster_background_list']}
    views = {r['poster_background_id']: r for r in pushes[32011]['sub_poster_background_list']}
    for cfg in unlock_catalog()['views']:
        assert cfg['view'] in views[cfg['scene_id']]['sub_background_list']
    assert {h['hero_base_info']['id'] for h in heroes} == set(HERO_DEFINITIONS)
    used_equips, used_servants = set(), set()
    for hero in heroes:
        base = hero['hero_base_info']
        hid = base['id']
        assert hero['unlock'] == 1 and (base['level'], base['star'], base['break_level']) == (100, 600, 8)
        assert all(s['skill_level'] == 35 for s in base['skill'])
        assert all(s['level'] == 15 for s in base['skill_intensify_attribute_list'])
        assert set(base['unlock_astrolabe']) == set(HERO_DEFINITIONS[hid][2])
        assert len(base['using_astrolabe']) == 3 and len(base['exclusive_skill_list']) == 6
        assert base['weapon_module_level'] == HERO_DEFINITIONS[hid][3]
        assert base['weapon']['exp'] == 99800 and base['weapon']['breakthrough'] == 4 and hero['trust']['level'] == 5
        assert {s['skin_id'] for s in hero['unlocked_skin']} == skins[hid]
        for pos, row in enumerate(hero['equip']):
            uid = row['equip_id']
            assert uid not in used_equips
            used_equips.add(uid)
            item = equipment[uid]
            assert item['prefab_id'] == HERO_LOADOUTS[hid][0][pos] and item['hero_id'] == item['race'] == hid
            assert item['exp'] > 0 and item['now_break_level'] > 0 and item['enchant_slot_list']
        uid = base['weapon']['servant_uid']
        assert uid not in used_servants
        used_servants.add(uid)
        assert servants[uid]['id'] == HERO_DEFINITIONS[hid][4] and servants[uid]['stage'] == 5


def test_unlock_command():
    """普通白号和已有配装均可解锁，错误参数不改存档，重复执行不扩库存。"""
    with isolated_accounts() as manager:
        user = manager.authenticate_password('满配指令隔离验证', 'isolated-test-password')
        uid = user['uid']
        before = deepcopy(user)
        for command in ('/unlock', '/unlock skin', '/unlock character extra'):
            assert not manager.apply_gm_command(uid, command)[0]
            assert manager.get_user_by_uid(uid) == before
        assert '/unlock character' in manager.apply_gm_command(uid, '/help')[1]
        session = server.ClientSession(MemoryWriter(), ('test', 1))
        session.user_id = uid
        request(session, 10042, {})
        server.CLIENT_SESSIONS[session.writer] = session
        balances = build_currency_balances(session.user_data)
        assert request(session, 27014, {'content': '/unlock character', 'type': 1})[27015]['result'] == 0
        assert_max_characters(read_pushes(session.writer))
        saved = manager.get_user_by_uid(uid)
        assert len(saved['equipment']) == 6 * len(HERO_DEFINITIONS)
        assert saved['level'] == 1 and build_currency_balances(saved) == balances
        scene = unlock_catalog()['views'][0]['scene_id']
        view = next(c['view'] for c in unlock_catalog()['views'] if c['scene_id'] == scene and c['view'] != 0)
        assert request(session, 32108, {'poster_background_id': scene})[32109]['result'] == 0
        assert request(session, 32134, {'poster_background_id': scene, 'sub_poster_background': view})[32135]['result'] == 0
        saved = manager.get_user_by_uid(uid)
        assert admin({'action': 'command', 'uid': uid, 'command': '$unlock character'})[0] == 200
        assert_max_characters(read_pushes(session.writer))
        assert manager.get_user_by_uid(uid) == saved
        # 对已养成账号再次执行时，提升已有实例并保留有效皮肤选择及背包物品。
        saved['heroes'][0]['skin_id'] = saved['heroes'][0]['skins'][-1]
        saved['heroes'][0]['battle_skin_id'] = saved['heroes'][0]['skins'][-1]
        saved['heroes'][0]['using_astrolabes'] = []
        saved['hero_preferences'] = {str(saved['heroes'][0]['id']): {'exclusive_skill_list': []}}
        saved['equipment'][0]['exp'] = 0
        saved['servants'][0]['stage'] = 1
        saved['equipment'].append({**saved['equipment'][0], 'equip_id': saved['next_equip_uid'], 'hero_id': 0})
        manager.save_user(saved)
        assert admin({'action': 'command', 'uid': uid, 'command': '/unlock character'})[0] == 200
        assert_max_characters(read_pushes(session.writer))
        restored = manager.get_user_by_uid(uid)
        assert len(restored['equipment']) == len(saved['equipment'])
        assert restored['heroes'][0]['skin_id'] == saved['heroes'][0]['skin_id']
        assert restored['heroes'][0]['battle_skin_id'] == saved['heroes'][0]['battle_skin_id']
        user_storage.UserManager._instance = None
        login = request(session, 10042, {})
        assert_max_characters(login)
        assert session.user_data['equipment'] == restored['equipment']
        assert session.user_data['heroes'] == restored['heroes'] and session.user_data['servants'] == restored['servants']
        assert login[32009]['poster_background_id'] == scene
        assert next(r for r in login[32011]['sub_poster_background_list']
                    if r['poster_background_id'] == scene)['current_sub_background'] == view
        assert session.user_data['scene_views'] == restored['scene_views']
    print('满配角色与全部场景 GM 指令、在线同步、切换、重复执行和重启恢复验证通过。')


if __name__ == '__main__':
    test_unlock_command()
