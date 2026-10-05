"""普通签到与累计签到的业务日初始化、领奖和持久化数据。"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from activity_data import build_available_activities
from item_catalog import give_items
from gameplay_protocol import read_client_data

SIGN_COMMANDS = {11010, 17028, 17030}


def business_date():
    """按北京时间每日 05:00 划分业务日。"""
    return (datetime.now(timezone(timedelta(hours=8))) - timedelta(hours=5)).date()


@lru_cache(maxsize=1)
def sign_catalog():
    """读取客户端的月份奖励、累计奖励和有效七日签到定义。"""
    return read_client_data('''(function()
        local r={daily={},accumulate={},seven={}}
        for _,name in ipairs({'SignCfg','AccumulateLoginCfg','ActivityCumulativeSignCfg'}) do
            local c=require(name);local key=({SignCfg='daily',AccumulateLoginCfg='accumulate',ActivityCumulativeSignCfg='seven'})[name]
            for _,id in ipairs(c.all) do r[key][#r[key]+1]=c[id] end
        end
        return r
    end)()''')


def initialize_sign(user):
    """同一业务日仅增加一次累计登录次数，跨月清除每日签到列表。"""
    today = business_date()
    state = user.setdefault('sign', {})
    month = today.strftime('%Y-%m')
    if state.get('month') != month:
        state.update(month=month, days=[])
    if state.get('login_date') != today.isoformat():
        state['login_days'] = state.get('login_days', 0) + 1
        state['login_date'] = today.isoformat()
    state.setdefault('award_ids', [])
    state.setdefault('open_sign', False)
    return state


def sign_pushes(user):
    """为普通页和累计页提供完整初始化，避免页面读取空签到数据。"""
    state = initialize_sign(user)
    today = business_date()
    result = [(11013, {'year': today.year, 'month': today.month, 'day': today.day, 'sign_list': state['days']}),
              (17027, {'version': 1, 'open_sign': state['open_sign'], 'login_days': state['login_days'], 'award_ids': state['award_ids']})]
    opened = {a['activity_id'] for a in build_available_activities() if a['state'] == 1}
    for cfg in sign_catalog()['seven']:
        if cfg['id'] in opened:
            saved = state.get('seven', {}).get(str(cfg['id']), {})
            result.append((11015, {'activity_id': cfg['id'], 'sign_count': saved.get('count', 0), 'last_sign_time': saved.get('time', 0)}))
    return result


def sign_request(user, command, request):
    """校验每日及累计领奖条件；重复请求不会重复发奖。"""
    state = initialize_sign(user)
    today = business_date()
    if command == 17028:
        state['open_sign'] = True
        return {'result': 0}
    if command == 17030:
        ids = request['id_list']
        configs = {c['id']: c for c in sign_catalog()['accumulate']}
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('累计签到奖励列表无效')
        rewards = []
        for item in ids:
            cfg = configs.get(item)
            if not cfg or cfg['version'] != 1 or cfg['num'] > state['login_days'] or item in state['award_ids']:
                raise ValueError('累计签到天数不足或奖励已领取')
            rewards.extend({'id': i, 'num': n} for i, n in cfg['reward'])
        rewards = give_items(user, rewards)
        state['award_ids'].extend(ids)
        return {'result': 0, 'item': rewards}
    aid = request['activity_id']
    if aid == 3:
        if today.day in state['days']:
            raise ValueError('今日已签到')
        cfg = next((c for c in sign_catalog()['daily'] if c['month'] == today.month and c['day'] == len(state['days']) + 1), None)
        if not cfg:
            raise ValueError('签到奖励配置缺失')
        rewards = give_items(user, [{'id': cfg['reward'][0], 'num': cfg['reward'][1]}])
        state['days'].append(today.day)
    else:
        cfg = next((c for c in sign_catalog()['seven'] if c['id'] == aid), None)
        if not cfg or aid not in {a['activity_id'] for a in build_available_activities() if a['state'] == 1}:
            raise ValueError('签到活动未开放')
        saved = state.setdefault('seven', {}).setdefault(str(aid), {'count': 0})
        if saved.get('date') == today.isoformat() or (saved['count'] >= len(cfg['config_list']) and not cfg['repeated']):
            raise ValueError('今日已签到或活动已签满')
        entry = cfg['config_list'][saved['count'] % len(cfg['config_list'])]
        reward = read_client_data(f"require('SignCfg')[{int(entry)}].reward")
        rewards = give_items(user, [{'id': reward[0], 'num': reward[1]}])
        import time
        saved.update(count=saved['count'] + 1, date=today.isoformat(), time=int(time.time()))
    return {'result': 0, 'item_list': rewards}
