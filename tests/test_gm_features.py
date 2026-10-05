"""用隔离磁盘、真实协议和原始客户端页面逻辑验证 GM、签到与邮件。"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import server
import user_storage
from account_unlocks import unlock_catalog
from communications import announcement_data
from currency_data import materialize_currencies
from gameplay_protocol import encode_message, decode_message
from gm_admin import gm_response, item_csv
from item_catalog import item_catalog
from proto_bridge import get_bridge
from tests.test_entry_flow import MemoryWriter
from tests.test_gameplay_persistence import request


@contextmanager
def isolated_accounts():
    """隔离所有新增存档目录，并在结束时恢复真实管理器与连接。"""
    previous = user_storage.UserManager._instance
    connections = dict(server.CLIENT_SESSIONS)
    with TemporaryDirectory() as directory:
        root = Path(directory)
        users, chat = root / 'users', root / 'chat'
        with patch.multiple(user_storage, DATA_DIR=root, USERS_DIR=users, CHAT_DIR=chat, META_FILE=users/'meta.json',
                            CHAT_FILE=chat/'world_chat.json', FRIEND_CHAT_FILE=chat/'friend_chat.json'):
            try:
                user_storage.UserManager._instance = None
                server.CLIENT_SESSIONS.clear()
                manager = user_storage.get_user_manager()
                yield manager
            finally:
                user_storage.UserManager._instance = previous
                server.CLIENT_SESSIONS.clear()
                server.CLIENT_SESSIONS.update(connections)


def admin(values=None, path='state', headers=None, peer=('127.0.0.1', 1)):
    """调用与 HTTP 路由相同的管理入口。"""
    method = 'GET' if values is None else 'POST'
    route = f'/gm/api/{path}' if values is None else '/gm/api/action'
    body, kind, code = gm_response(f'{method} {route} HTTP/1.1', json.dumps(values).encode() if values else b'',
        headers or {'host': '127.0.0.1:8081', 'content-type': 'application/json'}, peer,
        server.sync_online_account, server.sync_announcements, {s.user_id for s in server.CLIENT_SESSIONS.values()})
    return code, json.loads(body) if kind.startswith('application/json') else body


def test_gm_mail_and_restore():
    """通过管理入口发送附件、执行指令、更新公告，验证在线同步和重启幂等。"""
    with isolated_accounts() as manager:
        writer = MemoryWriter()
        session = server.ClientSession(writer, ('test', 1))
        login = request(session, 10042, {})
        user = manager.get_user_by_uid(10001)
        catalog = unlock_catalog()
        assert {s['id'] for s in login[46011]['servant_list']} == set(catalog['servants'])
        assert {s['id'] for s in login[52001]['servant_info']} == set(catalog['servants'])
        scenes = {s['id'] for s in login[32009]['poster_background_list']}
        assert not set(catalog['scenes']) <= scenes
        assert login[32011]['sub_poster_background_list'] == []
        playable = {h['id'] for h in user['heroes']}
        assert {(c['hero'], c['id']) for c in catalog['skins'] if c['hero'] in playable} == {
            (h['id'], s) for h in user['heroes'] for s in h['skins']}
        for kind, field in ((11, 'icon_list'), (12, 'icon_frame_list')):
            assert {i for i, row in item_catalog().items() if row['type'] == kind} <= {r['id'] for r in login[32009][field]}
        before_unlock = deepcopy(user)
        from account_unlocks import unlock_developer
        unlock_developer(user)
        assert user == before_unlock
        # 后台重复补齐不得替换账号已拥有的背景或视角。
        user['unlocked_decorations']['poster_background_list'] = [6059]
        user['scene_views'] = [{'poster_background_id': 6059, 'sub_background_list': [1], 'current_sub_background': 1}]
        user.pop('unlock_version')
        unlock_developer(user)
        assert user['unlocked_decorations']['poster_background_list'] == [6059]
        assert user['scene_views'][0]['current_sub_background'] == 1
        manager.save_user(user)
        server.CLIENT_SESSIONS[writer] = session
        for command in ('/flower 1234', '/gold 12345', '/diamond 54321', '/level 86'):
            assert admin({'action': 'command', 'uid': 10001, 'command': command})[0] == 200
        assert session.user_data['flower'] == 1234 and session.user_data['flower_ios'] == session.user_data['flower_free'] == 0
        assert session.user_data['currencies']['31'] == 1234
        assert writer.output
        frames = bytes(writer.output)
        pushes = {}
        import struct
        while frames:
            size = struct.unpack_from('>H', frames)[0]
            _, cmd, _, _, pb = server.unpack_ystcp(frames[2:2+size])
            pushes[cmd] = decode_message(cmd, pb, 'sc')
            frames = frames[2+size:]
        assert next(c['num'] for c in pushes[15009]['currency_list'] if c['id'] == 31) == 1234
        assert pushes[12009]['user_level'] == 86
        assert admin({'action': 'command', 'command': '/give 1 100'})[0] == 200
        assert manager.get_user_by_uid(10001)['diamond'] == 54421
        snapshot = manager.get_user_by_uid(10001)
        for command in ('/give 0 1', '/give 1 -1', '/give 1 0', '/give 1 2000000000', '/flower -1', '/gold 1 2'):
            assert admin({'action': 'command', 'command': command})[0] == 400
            assert manager.get_user_by_uid(10001) == snapshot
        for headers, peer in (({'host': 'example.com'}, ('127.0.0.1', 1)),
                              ({'host': '127.0.0.1:8081', 'origin': 'http://evil.example'}, ('127.0.0.1', 1)),
                              ({'host': '127.0.0.1:8081'}, ('192.168.1.2', 1))):
            assert admin(headers=headers, peer=peer)[0] == 403
        state = admin()[1]
        assert 'token' not in state['users'][0]
        notice = {'action': 'announcement', 'title': '测试公告', 'content': '公告正文', 'type': 101}
        assert admin(notice)[0] == 200
        assert announcement_data(manager)['announcement_list'][0]['title'] == '测试公告'
        assert admin({**notice, 'id': 1, 'title': '更新标题'})[0] == 200
        assert admin({'action': 'delete_announcement', 'id': 1})[0] == 200
        assert announcement_data(manager)['announcement_list'] == []
        second = manager.get_or_create_user('邮件测试账号')
        values = {'action': 'mail', 'uid': 0, 'title': '附件邮件', 'content': '持久化正文',
                  'rewards': [{'id': 1, 'num': 20}, {'id': 2, 'num': 30}]}
        assert admin(values)[0] == 200
        assert len(manager.get_user_by_uid(second['uid'])['mails']) == 1
        listed = request(session, 30002, {})
        assert set(listed) == {30003} and listed[30003]['total_num'] == 1
        detail = request(session, 30008, {'id': 1})
        assert set(detail) == {30009}
        assert detail[30009]['detail_info']['content_list'][0]['text'] == '持久化正文'
        with patch.object(manager, 'save_user', side_effect=AssertionError('邮件查询不应写盘')):
            assert set(request(session, 30002, {})) == {30003}
            assert set(request(session, 30020, {})) == {30021}
            assert set(request(session, 30008, {'id': 1})) == {30009}
        assert request(session, 30006, {'id': 1})[30007]['id_list'] == []
        claimed = request(session, 30004, {'id': 1})
        assert 30001 not in claimed
        rewards = claimed[30005]
        assert rewards['result'] == 0 and rewards['success_mail_ids'] == [1]
        snapshot = manager.get_user_by_uid(10001)
        assert request(session, 30004, {'id': 1})[30005]['result'] != 0
        assert manager.get_user_by_uid(10001) == snapshot
        claimed_list = request(session, 30002, {})[30003]['mail_list'][0]
        assert claimed_list['attach_flag'] == claimed_list['read_flag'] == 2
        assert set(request(session, 30014, {'mail_id': 1, 'opt': 1})) == {30015}
        collected = request(session, 30020, {})
        assert set(collected) == {30021} and collected[30021]['collect_total_num'] == 1
        assert set(request(session, 30022, {'mail_id': 1})) == {30023}
        # 真正重建存储对象，验证新登录恢复已领取、已读、收藏与 GM 余额。
        user_storage.UserManager._instance = None
        manager = user_storage.get_user_manager()
        restored = request(session, 10042, {})
        assert restored[30001]['unread_number'] == 0
        assert manager.get_user_by_uid(10001)['mails'][0]['claimed']
        assert manager.get_user_by_uid(10001)['diamond'] == 54441
        assert request(session, 30004, {'id': 0})[30005]['result'] != 0
        assert request(session, 30014, {'mail_id': 1, 'opt': 0})[30015]['result'] == 0
        assert request(session, 30006, {'id': 0})[30007]['id_list'] == [1]
        import csv
        from io import StringIO
        rows = list(csv.reader(StringIO(item_csv().decode('utf-8-sig'))))
        assert len(rows) == len(item_catalog()) + 1
        assert {int(row[0]) for row in rows[1:]} == set(item_catalog())


def test_sign_and_chapter_requests():
    """真实 CS/SC 检查签到幂等、跨月重置、剧情位置、事件及阅读持久化。"""
    with isolated_accounts() as manager:
        session = server.ClientSession(MemoryWriter(), ('test', 1))
        login = request(session, 10042, {})
        assert login[11013]['month'] > 0 and login[17027]['version'] == 1
        assert request(session, 11010, {'activity_id': 3})[11011]['result'] == 0
        snapshot = manager.get_user_by_uid(10001)
        assert request(session, 11010, {'activity_id': 3})[11011]['result'] != 0
        assert manager.get_user_by_uid(10001) == snapshot
        assert request(session, 17028, {})[17029]['result'] == 0
        from sign_progress import sign_catalog, initialize_sign
        reward = next(c for c in sign_catalog()['accumulate'] if c['version'] == 1)
        saved = manager.get_user_by_uid(10001)
        saved['sign']['login_days'] = reward['num']
        manager.save_user(saved)
        assert request(session, 17030, {'id_list': [reward['id']]})[17031]['result'] == 0
        snapshot = manager.get_user_by_uid(10001)
        assert request(session, 17030, {'id_list': [reward['id']]})[17031]['result'] != 0
        assert manager.get_user_by_uid(10001) == snapshot
        aid = next(v['activity_id'] for c, v in __import__('sign_progress').sign_pushes(snapshot) if c == 11015)
        assert request(session, 11010, {'activity_id': aid})[11011]['result'] == 0
        assert request(session, 11010, {'activity_id': aid})[11011]['result'] != 0
        with patch('sign_progress.business_date', return_value=date(2030, 2, 1)):
            assert initialize_sign(snapshot)['days'] == []
            count = snapshot['sign']['login_days']
            assert initialize_sign(snapshot)['login_days'] == count
        location = login[24061]['now_location']
        assert request(session, 24064, {'new_location': location})[24065]['result'] == 0
        assert request(session, 24064, {'new_location': 1})[24065]['result'] != 0
        from chapter_maps import map_catalog
        cfg = map_catalog()['events'][0]
        assert request(session, 24062, {'event_id': cfg['id']})[24063]['result'] == 0
        assert request(session, 24066, {'event_id': cfg['id']})[24067]['result'] == 0
        assert request(session, 56002, {'red_dot': 12345}) == {}
        assert request(session, 12100, {'language': 'zh_cn'})[12101]['result'] == 0
        assert request(session, 52014, {'id': unlock_catalog()['servants'][0], 'type': 3})[52015]['result'] == 0
        assert request(session, 32134, {'poster_background_id': 6049, 'sub_poster_background': 2})[32135]['result'] != 0
        owned = manager.get_user_by_uid(10001)
        owned['scene_views'] = [{'poster_background_id': 6049, 'sub_background_list': [2], 'current_sub_background': 0}]
        manager.save_user(owned)
        assert request(session, 32134, {'poster_background_id': 6049, 'sub_poster_background': 2})[32135]['result'] == 0
        user_storage.UserManager._instance = None
        restored = request(session, 10042, {})
        assert cfg['id'] in restored[24061]['event_list']
        assert restored[24061]['now_location'] == location
        assert restored[56001]['red_dot'] == [12345]
        assert restored[17027]['award_ids'] == [reward['id']]
        assert next(r for r in restored[32011]['sub_poster_background_list'] if r['poster_background_id'] == 6049)['current_sub_background'] == 2


def test_client_sign_page():
    """用原始 DailySignPage.RefreshSignItem 和数据类验证签到页初始化。"""
    from sign_progress import sign_pushes, business_date
    values = dict(sign_pushes({}))
    daily = encode_message(11013, values[11013]).hex()
    accumulate = encode_message(17027, values[17027]).hex()
    today = business_date()
    result = get_bridge().run_lua_expr(f'''(function()
        class=function() return {{}} end;singletonClass=class
        table.indexof=function(t,v) for i,x in ipairs(t)do if x==v then return i end end return false end
        table.keyof=table.indexof;table.nums=function(t)return #t end
        GameSetting=require('GameSetting');ActivityConst=require('ActivityConst')
        SignCfg=require('SignCfg');AccumulateLoginCfg=require('AccumulateLoginCfg')
        manager={{time={{GetDeltaToday=function()return {today.day} end,GetServerTime=function()return os.time()end,
            STimeDescS=function()return {today.year} end,CalcMonthDays=function()return 31 end}}}}
        local function message(c,hex)local m=require('p'..math.floor(c/1000)..'_pb')['sc_'..c]();m:ParseFromString(hex:gsub('..',function(b)return string.char(tonumber(b,16))end));return m end
        SignData=require('SignData');SignData:Init();SignData:InitDailySignData(message(11013,'{daily}'))
        AccumulateSignData=require('AccumulateSignData');AccumulateSignData:Init();AccumulateSignData:InitAccumulateSignData(message(17027,'{accumulate}'))
        SignTools=require('SignTools');BaseSignPage={{}}
        local noop=function()end;local item={{SetData=noop,Show=noop,RefreshCompleted=noop}}
        DailySignItem={{New=function()return item end}};CommonItemView={{New=function()return item end}}
        Object={{Instantiate=function()return {{}} end}};SetActive=noop
        local control={{SetSelectedIndex=noop,SetSelectedState=noop}}
        local page={{signItem_={{}},itemList_={{}},accumulateSlider_={{}},accumulateText_={{}},
            accuController_=control,itemNumController_=control,accuStateontroller_=control}}
        require('DailySignPage').RefreshSignItem(page)
        assert(#page.signItem_==31)
        assert(SignTools.GetDailySignIndex()==1)
        return '客户端原始签到页刷新通过'
    end)()''')
    print(result.decode())


if __name__ == '__main__':
    test_gm_mail_and_restore()
    test_sign_and_chapter_requests()
    test_client_sign_page()
    print('GM 在线同步、公告附件邮件、解锁、签到和剧情请求持久化验证通过。')
