"""用真实 CS/SC 和隔离磁盘覆盖探测、活动抽奖、白号及重启恢复。"""

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from unittest.mock import patch

import server
import user_storage
from account_defaults import new_account_defaults, player_levels
from battle_rewards import grant_rewards
from currency_data import build_currency_balances
from gacha_catalog import draw_catalog, draw_group, pool_details
from gacha_progress import award_draw, draw_state, pool_state, roll_item
from gameplay_protocol import encode_message, decode_message, read_client_data
from battle_progress import story_progress, progress_catalog
from hero_preferences import hero_info_data
from tests.test_entry_flow import MemoryWriter
from tests.test_gameplay_persistence import request
from tests.test_gm_features import isolated_accounts
from skin_draw_catalog import skin_catalog, skin_pools
from skin_draw_progress import skin_state, award_skin_drop


class FixedRandom:
    """确定性抽样仅用于触发边界，生产仍使用 SystemRandom。"""

    def __init__(self, probabilities=(0.999,)):
        """循环指定概率，固定从候选奖品中选第一项。"""
        self.values, self.index = probabilities, 0

    def random(self):
        """返回下一项测试概率。"""
        value = self.values[self.index % len(self.values)]
        self.index += 1
        return value

    def choice(self, rows):
        """固定选择第一项以核对 UP 与非 UP 路径。"""
        return rows[0]

    def choices(self, rows, weights, k):
        """检查动态权重均为正后选择第一项。"""
        assert len(rows) == len(weights) and all(w > 0 for w in weights) and k == 1
        return [rows[0]]


def test_pity_rules():
    """精确核对 10/40/70/90 边界、非 UP 和锚定池不额外保底。"""
    catalog = draw_catalog()
    for pid, limit in ((10002, 70), (3000801, 40), (4080101, 70), (5030301, 70), (5030601, 90)):
        pool = catalog['pools'][pid]
        selected = pool['optional_lists'][0]
        details = pool_details(pool, selected)
        group = {'ssr': limit - 1, 'a': 0, 's_guaranteed': False, 'a_guaranteed': False}
        state = {'first_ssr': False, 'newbie_closed': False}
        with patch('gacha_progress.RNG', FixedRandom()):
            item, rarity = roll_item(pool, group, details, state)
        assert rarity == 5
        if pool['pool_type'] in (2, 8, 6):
            assert item == selected and group['ssr'] == 0
        else:
            assert item != selected and group['ssr'] == 0 and group['s_guaranteed']
            with patch('gacha_progress.RNG', FixedRandom((0, 0.999))):
                assert roll_item(pool, group, details, state)[0] == selected
        group.update(ssr=0, a=9, s_guaranteed=False)
        with patch('gacha_progress.RNG', FixedRandom()):
            _, rarity = roll_item(pool, group, details, state)
        assert rarity == 4 and group['a'] == 0
    pool = catalog['pools'][5030601]
    details = pool_details(pool, pool['optional_lists'][0])
    group = {'ssr': 20, 'a': 0, 's_guaranteed': False, 'a_guaranteed': False}
    with patch('gacha_progress.RNG', FixedRandom((0, 0.999))):
        for _ in range(2):
            assert roll_item(pool, group, details, state)[0] != pool['optional_lists'][0]
    assert group['ssr'] == 22 and not group['s_guaranteed']
    pool = catalog['pools'][4080101]
    group.update(ssr=39, a=0)
    state['first_ssr'] = True
    with patch('gacha_progress.RNG', FixedRandom()):
        assert roll_item(pool, group, pool_details(pool, pool['optional_lists'][0]), state)[1] == 5
    assert not state['first_ssr']


def test_registered_account():
    """注册与登录后保持白号，拒绝无资金抽奖，真实扣款与记录随重启恢复。"""
    with isolated_accounts() as manager:
        user = manager.authenticate_password('抽奖隔离账号', 'isolated-test-password')
        session = server.ClientSession(MemoryWriter(), ('test', 1))
        session.user_data, session.user_id = user, user['uid']
        replies = request(session, 10042, {'user_id': user['uid'], 'account': user['account'], 'gstoken': user['token']})
        assert replies[10043]['result'] == 0 and replies[12009]['user_level'] == 1
        user = session.user_data
        assert [h['id'] for h in user['heroes']] == [1084]
        assert all(n == (100 if i == 4 else 0) for i, n in build_currency_balances(user).items())
        chapters = replies[24009]['user_chapter_list']
        assert {r['id'] for r in chapters} == {r['id'] for r in progress_catalog()['story']}
        assert all(r['clear_times'] == 1 and r['star_list'] == [0, 0, 0] for r in chapters)
        assert not user['battle_progress']
        played = deepcopy(user)
        stage_id = next(r['id'] for r in progress_catalog()['story'] if r['star_count'] == 3)
        played['battle_progress'][f'1:{stage_id}'] = {'clear_times': 5, 'stars': [1, 3]}
        assert next(r for r in story_progress(played)['user_chapter_list'] if r['id'] == stage_id) == {
            'id': stage_id, 'clear_times': 5, 'star_list': [1, 0, 1]}
        assert replies[12011] and replies[12111]
        pool = draw_catalog()['pools'][5030301]
        up = pool['optional_lists'][0]
        assert request(session, 16016, {'id': pool['id'], 'up': up})[16017]['result'] == 0
        snapshot = manager.get_user_by_uid(user['uid'])
        assert request(session, 16016, {'id': pool['id'], 'up': 9999999})[16017]['result'] != 0
        assert manager.get_user_by_uid(user['uid']) == snapshot
        values = {'pool': pool['id'], 'type': 10, 'cost': {'id': 38, 'num': 10}}
        assert request(session, 16010, values)[16011]['result'] != 0
        assert manager.get_user_by_uid(user['uid']) == snapshot
        grant_rewards(snapshot, [{'id': 38, 'num': 100}])
        manager.save_user(snapshot)
        real_encode = server.encode_message

        def fail_reward_encode(command, values, direction='sc'):
            """模拟成功奖包编码失败，核对不会提交已扣费的克隆存档。"""
            if command == 16011 and values['result'] == 0:
                raise ValueError('隔离测试编码失败')
            return real_encode(command, values, direction)

        with patch.object(server, 'encode_message', side_effect=fail_reward_encode):
            assert request(session, 16010, values)[16011]['result'] != 0
        assert manager.get_user_by_uid(user['uid']) == snapshot
        with patch('gacha_progress.RNG', FixedRandom()):
            reply = request(session, 16010, values)
        assert reply[16011]['result'] == 0 and len(reply[16011]['item']) == 10
        assert build_currency_balances(session.user_data)[38] == 90
        assert build_currency_balances(session.user_data)[36] == 110
        assert build_currency_balances(session.user_data)[9] == 0
        assert next(r['num'] for r in reply[15009]['currency_list'] if r['id'] == 36) == 110
        assert session.user_data['draw']['groups']['3']['ssr'] == 10
        assert len(session.user_data['servants']) == 9 and len(session.user_data['heroes']) == 2
        assert all(h['level'] == 1 for h in session.user_data['heroes'])
        details = request(session, 16018, {'id': pool['id']})[16019]
        assert details['pool_details']['s_up_item'] and details['result'] == 0
        records = request(session, 16012, {'id': pool['id']})[16013]['draw_record_list']
        assert len(records) == 10 and all(r['draw_timestamp'] > 0 for r in records)
        assert request(session, 16016, {'id': pool['id'], 'up': pool['optional_lists'][1]})[16017]['result'] == 0
        assert session.user_data['draw']['groups']['3']['ssr'] == 10
        snapshot = deepcopy(session.user_data)
        user_storage.UserManager._instance = None
        manager = user_storage.get_user_manager()
        restored = manager.get_user_by_uid(user['uid'])
        assert restored['draw'] == snapshot['draw'] and restored['servants'] == snapshot['servants']
        assert build_currency_balances(restored)[36] == 110
        replies = request(session, 10042, {'user_id': restored['uid'], 'account': restored['account'], 'gstoken': restored['token']})
        assert replies[16015]['today_draw_times'] == 10
        assert session.user_data['heroes'] == snapshot['heroes'] and session.user_data['level'] == 1
        initial = new_account_defaults()
        initial['nick'] = '成长验证'
        grant_rewards(initial, [{'id': 12, 'num': player_levels()[0]['exp']}])
        assert initial['level'] == 2
        grant_rewards(initial, [{'id': 1039, 'num': 1}, {'id': 1039, 'num': 1}])
        assert any(h['id'] == 1039 for h in initial['heroes']) and initial['hero_pieces']['1039'] == 30
        newbie = draw_catalog()['pools'][3000801]
        for i in newbie['optional_lists'][:3]:
            assert request(session, 16016, {'id': newbie['id'], 'up': i})[16017]['result'] == 0
        assert request(session, 16016, {'id': newbie['id'], 'up': newbie['optional_lists'][3]})[16017]['result'] != 0


def test_skin_draws():
    """普通与翻牌池耗尽、重复请求、独立皮肤解锁及存盘恢复。"""
    with isolated_accounts() as manager:
        user = manager.authenticate_password('皮肤隔离账号', 'isolated-test-password')
        for pool in skin_pools():
            grant_rewards(user, [{'id': pool['cost_once'][0], 'num': 100}])
        manager.save_user(user)
        session = server.ClientSession(MemoryWriter(), ('test', 1))
        session.user_data, session.user_id = user, user['uid']
        session.token = user['token']
        for pool in skin_pools():
            oath = pool['pool_id'] in (1025, 1026)
            command = 68186 if oath else 68152
            values = {'activity_id': pool['activity_id'][0], 'pool_id': pool['pool_id'],
                      'card_index' if oath else 'drop_type': 0 if oath else 10}
            total = sum(d['total'] for d in skin_catalog()['drops'].values() if d['pool_id'] == pool['pool_id'])
            with patch('skin_draw_progress.RNG', FixedRandom()):
                while True:
                    reply = request(session, command, values)
                    assert reply[command + 1]['result'] == 0
                    state = skin_state(session.user_data, pool)
                    if not sum(state['remaining'].values()):
                        break
            assert len(state['records']) == total
            assert build_currency_balances(session.user_data)[pool['cost_once'][0]] == 100 - total
            snapshot = manager.get_user_by_uid(user['uid'])
            assert request(session, command, values)[command + 1]['result'] != 0
            assert manager.get_user_by_uid(user['uid']) == snapshot
        skins = session.user_data['owned_skins']
        assert 108502 in skins and 109503 in skins and [h['id'] for h in session.user_data['heroes']] == [1084]
        hero_data = hero_info_data(session.user_data)
        assert all(h['unlock'] == int(h['hero_base_info']['id'] == 1084) for h in hero_data['hero_info_list'])
        assert request(session, 68156, {'skin_id': 108502})[68157]['result'] == 0
        snapshot = manager.get_user_by_uid(user['uid'])
        assert request(session, 68156, {'skin_id': 108502})[68157]['result'] != 0
        assert manager.get_user_by_uid(user['uid']) == snapshot
        user_storage.UserManager._instance = None
        restored = user_storage.get_user_manager().get_user_by_uid(user['uid'])
        assert restored['skin_draw'] == snapshot['skin_draw'] and restored['owned_skins'] == skins
        grant_rewards(restored, [{'id': 1085, 'num': 1}])
        assert 108502 in next(h['skins'] for h in restored['heroes'] if h['id'] == 1085)


def test_duplicate_rewards():
    """重复角色返情报和辉芒；重复永久皮肤兑换，不再次解锁角色。"""
    user = new_account_defaults()
    result = award_draw(user, 1084)
    assert result['convert_from'] == {'id': 1084, 'num': 1}
    assert user['hero_pieces']['1084'] == 20 and build_currency_balances(user)[36] == 10
    assert build_currency_balances(user)[9] == 0
    grant_rewards(user, [{'id': 108502, 'num': 1}])
    drop = next(d for d in skin_catalog()['drops'].values()
                if d['pool_id'] == 1023 and d['reward'][0][0] == 108502)
    exchange = skin_catalog()['items']['108502']['exchange']
    assert exchange
    award_skin_drop(user, drop)
    assert build_currency_balances(user)[exchange[0][0]] == exchange[0][1]
    assert user['owned_skins'] == [108502] and len(user['heroes']) == 1
    encode_message(14009, hero_info_data(user))


def test_draw_currency():
    """按真实物品名称确认辉芒，并覆盖各品质角色和钥从的实际入账。"""
    assert read_client_data("require('ItemCfg')[36].name") == '共鸣辉芒'
    catalog = draw_catalog()
    for kind, rarity_field, offset in (('heroes', 'rare', 2), ('servants', 'starlevel', 0)):
        for rarity, amount in ((3, 10), (4, 20), (5, 100)):
            item = next(int(i) for i, cfg in catalog[kind].items() if cfg[rarity_field] + offset == rarity)
            user = new_account_defaults()
            award_draw(user, item)
            assert build_currency_balances(user)[36] == amount
            assert build_currency_balances(user)[9] == 0


if __name__ == '__main__':
    with redirect_stdout(StringIO()):
        test_pity_rules()
        test_registered_account()
        test_skin_draws()
        test_duplicate_rewards()
        test_draw_currency()
    print('探测、皮肤抽奖和初始白号协议与持久化验证通过。')
