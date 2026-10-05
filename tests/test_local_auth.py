"""使用隔离磁盘和真实客户端协议验证私服账号认证。"""

import base64
import hashlib
import json
import struct
from copy import deepcopy

import server
import user_storage
from account_auth import sdk_user_id
from gameplay_protocol import decode_message, encode_message
from tests.test_entry_flow import MemoryWriter
from tests.test_gm_features import isolated_accounts
from tests.test_gameplay_persistence import request


def sdk(path, values=None, headers=None):
    """通过生产 HTTP 路由提交认证请求。"""
    body, _ = server.route_http_response('POST ' + path + ' HTTP/1.1', json.dumps(values or {}).encode(), headers)
    return json.loads(body)


def game_login(command, values, session):
    """发送真实登录 protobuf 并解码首个响应。"""
    response = server.handle_tcp_message(2048, 0, 0,
        struct.pack('<IHH', command, 2, 0) + encode_message(command, values, 'cs'), session=session)
    length = struct.unpack_from('>H', response)[0]
    _, reply, _, _, body = server.unpack_ystcp(response[2:2+length])
    return decode_message(reply, body, 'sc')


def test_authentication():
    """注册、错误密码、缓存令牌、重启恢复与跨账号拒绝均须通过真实路由。"""
    with isolated_accounts() as manager:
        developer = manager.get_user_by_uid(10001)
        developer['reserve_test_marker'] = {'team': [1084, 1011]}
        manager.save_user(developer)
        first = sdk('/sdk-api/pass/user/login', {'username': 'developer', 'password': 'local-password'})
        assert first['errorCode'] == '0' and first['data']['phone'] == 'Developer'
        developer = manager.get_user_by_uid(10001)
        assert developer['nick'] == 'Developer' and developer['reserve_test_marker']['team'] == [1084, 1011]
        raw = user_storage.USERS_DIR.joinpath('10001.json').read_text(encoding='utf-8')
        assert 'local-password' not in raw and developer['password_auth']['iterations'] >= 210_000
        before = deepcopy(developer)
        wrong = sdk('/sdk-api/pass/user/login', {'username': 'Developer', 'password': 'wrong'})
        assert wrong['errorCode'] != '0' and wrong['errorMsg'] == '账号或密码错误'
        assert manager.get_user_by_uid(10001) == before
        password = '新账号密码'
        encoded = hashlib.md5(password.encode()).hexdigest()[:8].upper() + base64.b64encode(password.encode()).decode()
        registered = sdk('/sdk-api/pass/user/login', {'username': '测试账号', 'password': encoded, 'encode': 'true'})
        assert registered['errorCode'] == '0'
        user = manager.get_user_by_uid(10002)
        assert user['nick'] == user['account'] == '测试账号'
        assert user['password_auth']['salt'] != developer['password_auth']['salt']
        channel = {'errorCode': '0', 'errorMsg': '', 'data': registered['data']}
        mixed = sdk('/mix-sdk-api/pass/user/login', {'channelLoginRespInfo': json.dumps(channel)})
        assert mixed['data']['id'] == sdk_user_id(user) and mixed['data']['token'] == user['token']
        channel['data']['userId'] = sdk_user_id(developer)
        assert sdk('/mix-sdk-api/pass/user/login', {'channelLoginRespInfo': json.dumps(channel)})['errorCode'] != '0'
        assert sdk('/sdk-api/pass/user/loginBySms', {'phone': '测试账号'})['errorCode'] != '0'
        assert sdk('/mix-sdk-api/pass/user/login', {'channelLoginRespInfo': '{'})['errorMsg'] == '渠道登录信息格式错误'
        assert sdk('/sdk-api/pass/user/loginByToken', {}, {'token': user['token']})['data']['userId'] == sdk_user_id(user)
        assert sdk('/sdk-api/pass/user/loginByToken', {'token': 'dev_mock_token_12345'})['errorCode'] != '0'
        session = server.ClientSession(MemoryWriter(), ('test', 1))
        assert game_login(10038, {'account': str(sdk_user_id(user)), 'token': user['token']}, session)['user_id'] == user['uid']
        assert game_login(10042, {'user_id': developer['uid'], 'account': developer['account'], 'gstoken': user['token']}, session)['result'] != 0
        assert game_login(10042, {'user_id': user['uid'], 'account': str(sdk_user_id(user)), 'gstoken': user['token']}, session)['result'] == 0
        assert session.user_id == user['uid']
        assert request(session, 32012, {'sign': '新账号独立存档'})[32013]['result'] == 0
        assert manager.get_user_by_uid(10001).get('sign') != '新账号独立存档'
        user_storage.UserManager._instance = None
        restarted = user_storage.get_user_manager()
        assert restarted.authenticate_token(user['token'])['uid'] == user['uid']
        assert restarted.authenticate_token(developer['token'])['uid'] == developer['uid']
        relogin = sdk('/sdk-api/pass/user/login', {'username': '测试账号', 'password': password})
        assert relogin['errorCode'] == '0' and relogin['data']['token'] != user['token']
        assert restarted.authenticate_token(user['token']) is None
        assert server.handle_tcp_message(2048, 0, 0, struct.pack('<IHH', 10050, 1, 0), session=session) is None
        assert session.closed
        new_token = relogin['data']['token']
        assert sdk('/sdk-api/auth/user/logout', {}, {'token': new_token})['errorCode'] == '0'
        assert restarted.authenticate_token(new_token) is None
        unauthenticated = server.ClientSession(MemoryWriter(), ('test', 2))
        response = server.handle_tcp_message(2048, 0, 0, struct.pack('<IHH', 32012, 1, 0), session=unauthenticated)
        assert response is None and unauthenticated.closed
        print('账号注册、密码校验、SDK/游戏会话绑定、独立存档与重启恢复验证通过')


if __name__ == '__main__':
    test_authentication()
