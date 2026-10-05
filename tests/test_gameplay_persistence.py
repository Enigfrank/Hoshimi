"""使用真实协议和隔离磁盘存档，验证修改、重启恢复和重复领奖。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import asyncio
import struct

import server
import user_storage
from battle_data import settle_battle
from battle_data import start_battle
from challenge_requests import challenge_request
from challenge_data import challenge_pushes
from battle_udp import BattleUDP
from gameplay_protocol import decode_message, encode_message
from hero_data import build_max_heroes
from hero_preferences import hero_info_data
from reserve_data import save_reserve, reserve_data
from tests.test_entry_flow import MemoryWriter


def request(session, command, values):
    """将真实 CS 编码交给服务器，再解析对应的 SC 结果。"""
    if command == 10042 and not values:
        manager = user_storage.get_user_manager()
        user = manager.get_user_by_uid(session.user_id or 10001)
        if not user.get('password_auth'):
            user = manager.authenticate_password(user['account'], 'isolated-test-password')
        values = {'user_id': user['uid'], 'account': user['account'], 'gstoken': user['token']}
    elif session.user_data and not session.user_id:
        if not session.user_data.get('password_auth'):
            session.user_data = user_storage.get_user_manager().authenticate_password(
                session.user_data['account'], 'isolated-test-password')
        session.user_id = session.user_data['uid']
        session.account = session.user_data['account']
        session.token = session.user_data['token']
    payload = struct.pack('<IHH', command, 9, 0) + encode_message(command, values, 'cs')
    raw = server.handle_tcp_message(2048, 0, 0, payload, session=session)
    responses = {}
    while raw:
        size = struct.unpack_from('>H', raw)[0]
        _, cmd, _, _, pb = server.unpack_ystcp(raw[2:2+size])
        responses[cmd] = decode_message(cmd, pb, 'sc')
        raw = raw[2+size:]
    return responses


def test_disk_restore():
    """保存角色、编队和名片，模拟服务器重建并验证登录恢复及 GM 防覆盖。"""
    previous = user_storage.UserManager._instance
    with TemporaryDirectory() as directory:
        root = Path(directory)
        users, chat = root/'users', root/'chat'
        with patch.multiple(user_storage, USERS_DIR=users, CHAT_DIR=chat, META_FILE=users/'meta.json',
                            CHAT_FILE=chat/'world_chat.json', FRIEND_CHAT_FILE=chat/'friend_chat.json'):
            try:
                user_storage.UserManager._instance = None
                manager = user_storage.get_user_manager()
                user = manager.get_user_by_uid(10001)
                user['heroes'] = build_max_heroes()
                manager.save_user(user)
                session = server.ClientSession(MemoryWriter(), ('test', 1))
                session.user_data = user
                assert request(session, 32016, {'poster_girl': 1011})[32017]['result'] == 0
                assert request(session, 32012, {'sign': '持久化验证'})[32013]['result'] == 0
                assert request(session, 12030, {'month': 2, 'day': 29})[12031]['result'] == 0
                assert request(session, 14106, {'hero_id': 1084})[14107]['result'] == 0
                assert request(session, 14046, {'hero_id': 1084, 'skin_id': 108403})[14047]['result'] == 0
                assert request(session, 14040, {'hero_id': 1084})[14041]['result'] == 0
                assert request(session, 13018, {'hero_id': 1084})[13019]['result'] == 0
                assert request(session, 13012, {'hero_id': 1084, 'equip_id': 10841, 'pos': 1})[13013]['result'] == 0
                assert request(session, 46014, {'uid': 1084, 'is_lock': 0})[46015]['result'] == 0
                assert request(session, 46020, {'hero_id': 1084, 'servant_id': 0})[46021]['result'] == 0
                proposal = request(session, 13036, {'hero_id': 1084, 'proposal_name': '刻印方案'})[13037]
                assert proposal['result'] == 0 and proposal['proposal_id'] > 0
                assert request(session, 13038, {'hero_id': 0, 'proposal_id': proposal['proposal_id'],
                    'proposal_name': '重命名方案'})[13039]['result'] == 0
                assert request(session, 50002, {'id': 101})[50003]['result'] == 0
                assert request(session, 50008, {'id': 1, 'name': '芯片方案', 'secondary': [101]})[50009]['result'] == 0
                assert request(session, 34032, {'id': 33001, 'is_pay': 0})[34033]['result'] == 0
                passport_snapshot = manager.get_user_by_uid(10001)
                assert request(session, 34032, {'id': 33001, 'is_pay': 0})[34033]['result'] != 0
                assert manager.get_user_by_uid(10001) == passport_snapshot
                # 最新磁盘余额必须胜过旧会话中的余额。
                manager.modify_currency(10001, gold=54321)
                assert request(session, 32012, {'sign': '更新签名'})[32013]['result'] == 0
                assert manager.get_user_by_uid(10001)['gold'] == 54321
                from currency_data import build_currency_balances
                assert build_currency_balances(manager.get_user_by_uid(10001))[2] == 54321
                team = {'team_index': 0, 'hero_list': [{'hero_id': 1084, 'hero_type': 1}],
                        'cooperate_unique_skill_id': 0, 'mimir_info': {}}
                for container in (1, 2):
                    values = {'team_type': 9999, 'cont_team': {'cont_id': container, 'teams': [team]},
                              'data': {'cont_id': container, 'name': f'方案{container}', 'tags': [container]}}
                    assert request(session, 63010, values)[63011]['result'] == 0
                # 真正重新初始化管理器，而非只检查修改后的内存字典。
                user_storage.UserManager._instance = None
                manager = user_storage.get_user_manager()
                new_session = server.ClientSession(MemoryWriter(), ('test', 2))
                login = request(new_session, 10042, {})
                assert login[32009]['poster_girl'] == 1011 and login[32009]['sign'] == '更新签名'
                assert login[12033] == {'month': 2, 'day': 29}
                assert login[14009]['favorites'] == [1084]
                hero = next(h for h in login[14009]['hero_info_list'] if h['hero_base_info']['id'] == 1084)
                assert hero['hero_base_info']['battle_using_skin'] == 108403
                assert hero['hero_base_info']['using_astrolabe'] == []
                assert hero['hero_base_info']['weapon']['servant_uid'] == 0
                assert [e['equip_id'] for e in hero['equip']] == [10841, 0, 0, 0, 0, 0]
                assert login[14009]['proposal_list'][0]['name'] == '重命名方案'
                assert next(s for s in login[46011]['servant_list'] if s['uid'] == 1084)['is_locked'] == 0
                assert login[50001]['unlock_secondary_chip'] == [101]
                assert login[50001]['proposals'][0]['secondary'] == [101]
                assert login[34031]['receive_info'] == [{'id': 33001, 'is_pay': 0}]
                plans = login[63005]['formation_teams_info_list'][0]['data']
                assert {p['name'] for p in plans} == {'方案1', '方案2'}
                # 登录任务仅发放一次，重复请求不增加库存。
                first = request(new_session, 28010, {'id': 6001})[28011]
                assert first['result'] == 0 and first['reward_list']
                snapshot = manager.get_user_by_uid(10001)
                assert request(new_session, 28010, {'id': 6001})[28011]['result'] != 0
                assert manager.get_user_by_uid(10001) == snapshot
                # 动态补给按服务器价格扣款，客户传入虚假 cost_items 无法免费获得商品。
                before = snapshot['diamond']
                response = request(new_session, 20012, {'shop_id': 3, 'buy_source': 0,
                    'buy_goods_list': [{'buy_id': 900020001, 'buy_num': 2, 'buy_type': 0, 'cost_items': []}]})[20013]
                assert response['result'] == 0
                after = manager.get_user_by_uid(10001)
                assert after['diamond'] == before-2 and after['shop_purchases']['3']['900020001'] == 2
                stock = request(new_session, 10042, {})[20009]
                shop = next(s for s in stock['shop_item_list'] if s['shop_id'] == 3)
                assert next(g for g in shop['goods_list'] if g['goods_id'] == 900020001)['buy_times'] == 2
            finally:
                user_storage.UserManager._instance = previous


def test_real_result_idempotent():
    """只有实际胜利上报才推进进度，重复结算不重复发货。"""
    user = {'gold': 0, 'stamina': 240}
    battle = {'id': 17, 'started': 0, 'config': {'cost': 0, 'three_star_need': [[8, 1], [4, 60]]},
              'common': {'type': 2, 'dest': 2010101, 'battle_times': 1, 'hero_list': [{'hero_id': 1084}]},
              'reported': {'result': 1, 'info': {'2': 38000}}, 'settlement': None}
    with patch('battle_data.roll_drops', return_value=[{'id': 2, 'num': 2100}]):
        result = settle_battle(user, battle, 17)
        assert result['battle_result']['use_seconds'] == 38
        assert all(s['is_achieve'] for s in result['battle_result']['star_list'])
        snapshot = deepcopy(user)
        assert settle_battle(user, battle, 17) == result and user == snapshot


def test_challenge_routes():
    """终末黑区队伍序号映射为真实关卡，重置不能重复领取通关奖励。"""
    user = {'uid': 10001, 'heroes': build_max_heroes(), 'stamina': 240}
    battle, _ = start_battle(user, {'common_info': {'type': 35, 'dest': 1, 'battle_times': 1,
        'hero_list': [{'hero_id': 1084, 'hero_type': 1}]}})
    assert battle['config']['id'] == 3028001
    battle['reported'] = {'result': 1, 'info': {'2': 30000}}
    settle_battle(user, battle, battle['id'])
    assert user['mythic_final_cleared'] == [1]
    assert challenge_request(user, 44028, {'difficulty_id': 1})['item_list']
    challenge_request(user, 44026, {})
    try:
        challenge_request(user, 44028, {'difficulty_id': 1})
        raise AssertionError('重置后重复领取了奖励')
    except ValueError:
        pass
    user['mythic_difficulty'] = 1001
    pushes = dict(challenge_pushes(user))
    assert pushes[44019]['difficulty'] == 1001
    assert pushes[44023]['receive_reward'] == [1]


async def test_udp_fragments_and_retry():
    """模拟乱序分片、重复 PUSH、丢失 ACK 与重传，验证消息不被重复执行。"""
    class Transport:
        """收集 UDP 输出，不监听真实端口。"""
        def __init__(self):
            """初始化发送记录。"""
            self.sent = []
        def sendto(self, packet, address):
            """记录输出用于确认和重传断言。"""
            self.sent.append((packet, address))
    received = []
    def handle(packet, context):
        """完整消息只执行一次，并返回需要分片的响应。"""
        received.append(packet)
        return [b'x'*1000]
    endpoint = BattleUDP(handle)
    endpoint.transport = Transport()
    address = ('test', 7)
    endpoint.datagram_received(struct.pack('<BII', 1, 100, 0), address)
    channel = endpoint.channels[address]
    def segment(sn, fragment, payload, cmd=81):
        """构造客户端 KCP 输入段。"""
        return struct.pack('<BI', 4, channel['local']) + struct.pack(
            '<IBBHIIII', channel['local'], cmd, fragment, 256, 0, sn, 0, len(payload)) + payload
    endpoint.datagram_received(segment(1, 0, b'end'), address)
    assert received == []
    endpoint.datagram_received(segment(0, 1, b'first'), address)
    endpoint.datagram_received(segment(0, 1, b'first'), address)
    assert received == [b'firstend'] and len(channel['pending']) == 3
    for sn, (packet, _) in list(channel['pending'].items()):
        channel['pending'][sn] = (packet, 0)
    count = len(endpoint.transport.sent)
    endpoint.tick()
    assert len(endpoint.transport.sent) == count+3
    for sn in list(channel['pending']):
        endpoint.datagram_received(segment(sn, 0, b'', 82), address)
    assert channel['pending'] == {}
    endpoint.connection_lost(None)


if __name__ == '__main__':
    test_disk_restore()
    test_real_result_idempotent()
    test_challenge_routes()
    asyncio.run(test_udp_fragments_and_retry())
    print('存档重启、GM 防覆盖、角色配置、编队方案、交易、重复领奖及 UDP 重传验证通过。')
