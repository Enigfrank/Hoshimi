"""私服密码散列及客户端 SDK 认证协议。"""

import base64
import hashlib
import hmac
import secrets
from urllib.parse import parse_qs, urlsplit
import json

PASSWORD_ITERATIONS = 210_000


def sdk_user_id(user: dict) -> int:
    """提供 Int64 SDK 身份；客户端 LitJson 无法把小整数转换为 Int64。"""
    return user['uid'] + 2**32


def matches_game_account(user: dict, account: str) -> bool:
    """SDK 身份与游戏 UID 均通过有效令牌绑定到同一个私服存档。"""
    return account in (user['account'], str(user['uid']), str(sdk_user_id(user)))


def password_record(password: str) -> dict:
    """保存随机盐和 PBKDF2 散列，不保存原始密码。"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PASSWORD_ITERATIONS)
    return {'salt': salt, 'iterations': PASSWORD_ITERATIONS, 'digest': digest.hex()}


def password_matches(password: str, record: dict) -> bool:
    """以恒定时间比较密码散列。"""
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(record['salt']), record['iterations'])
    return hmac.compare_digest(digest.hex(), record['digest'])


def request_values(line: str, body: bytes) -> dict:
    """兼容 SDK 表单、JSON 消息体及 GET 查询参数。"""
    target = line.split(' ')[1]
    values = {k: v[-1] for k, v in parse_qs(urlsplit(target).query).items()}
    if body:
        try:
            parsed = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            try:
                parsed = {k: v[-1] for k, v in parse_qs(body.decode('utf-8')).items()}
            except UnicodeDecodeError as error:
                raise ValueError('认证请求编码错误') from error
        if not isinstance(parsed, dict):
            raise ValueError('认证请求格式错误')
        values.update(parsed)
    return values


def sdk_password(values: dict) -> str:
    """还原 SDK 的八位 MD5 前缀加 Base64 编码，并校验前缀。"""
    password = values.get('password', '')
    if not isinstance(password, str):
        raise ValueError('密码格式错误')
    if str(values.get('encode', '')).lower() == 'true':
        try:
            raw = base64.b64decode(password[8:], validate=True)
            if not hmac.compare_digest(hashlib.md5(raw).hexdigest()[:8].upper(), password[:8]):
                raise ValueError('密码编码错误')
            password = raw.decode('utf-8')
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError('密码编码错误') from error
    return password


def sdk_result(user: dict = None, error: str = '', mix: bool = False) -> dict:
    """按客户端 SDK 格式返回认证成功或可显示的中文错误。"""
    if error:
        return {'code': 1, 'errorCode': '1', 'message': error, 'errorMsg': error, 'data': None}
    data = {'userId': sdk_user_id(user), 'phone': user['account'], 'nickName': user['account'],
            'token': user['token'], 'realNameValid': True, 'adult': True,
            'guest': False, 'indulgeLimitStatus': '0', 'regionNo': '86'}
    if mix:
        data = {'id': sdk_user_id(user), 'nickName': user['account'], 'channelUserId': str(sdk_user_id(user)),
                'channelUserNickName': user['account'], 'token': user['token'],
                'enableLogin': True, 'enableNewRole': True, 'enablePay': False,
                'createDate': user['created_at'] * 1000, 'extraData': '{}'}
    return {'code': 0, 'errorCode': '0', 'errorMsg': '', 'message': 'success', 'data': data}


def sdk_authenticate(line: str, body: bytes, headers: dict, manager) -> dict:
    """私服验证密码或登录令牌，禁止短信与第三方接口绕过认证。"""
    try:
        values = request_values(line, body)
        path = urlsplit(line.split(' ')[1]).path.rstrip('/')
        action = path.rsplit('/', 1)[-1]
        if action == 'logout':
            manager.revoke_token(values.get('token') or headers.get('token', ''))
            return {'code': 0, 'errorCode': '0', 'message': 'success', 'data': {}}
        if (path.startswith('/mix-sdk-api/') and action == 'login') or action == 'loginByToken':
            token = values.get('token') or headers.get('token', '')
            channel_user_id = None
            if path.startswith('/mix-sdk-api/') and 'channelLoginRespInfo' in values:
                try:
                    info = json.loads(values['channelLoginRespInfo'])
                except (ValueError, TypeError) as error:
                    raise ValueError('渠道登录信息格式错误') from error
                if not isinstance(info, dict) or str(info.get('errorCode')) != '0' or not isinstance(info.get('data'), dict):
                    raise ValueError('渠道登录信息格式错误')
                token = info['data'].get('token', '')
                channel_user_id = info['data'].get('userId')
            user = manager.authenticate_token(token)
            if not user:
                raise ValueError('登录已失效，请输入账号密码重新登录')
            if path.startswith('/mix-sdk-api/') and 'channelLoginRespInfo' in values and channel_user_id != sdk_user_id(user):
                raise ValueError('账号与登录令牌不匹配')
            return sdk_result(user, mix=path.startswith('/mix-sdk-api/'))
        if path.startswith('/sdk-api/') and action in ('login', 'loginByLoginName'):
            account = values.get('username') or values.get('loginName') or ''
            return sdk_result(manager.authenticate_password(account, sdk_password(values)))
        raise ValueError('私服请使用密码登录；新账号会自动注册')
    except (ValueError, TypeError) as error:
        return sdk_result(error=str(error))
