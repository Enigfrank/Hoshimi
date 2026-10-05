"""每日兑换、体力领取和新手奖励的持久化。"""

from functools import lru_cache
import time

from battle_rewards import grant_rewards, spend_items
from gameplay_protocol import read_client_data
from currency_data import build_currency_balances
from server_clock import business_day, refresh_hour

DAILY_COMMANDS = {15012, 15016, 15020, 12046, 59002, 59004, 59012, 59014}


def server_day(timestamp: int) -> int:
    """按客户端的北京时间每日刷新时刻划分领取日期。"""
    return business_day(timestamp)


@lru_cache(maxsize=1)
def daily_catalog() -> dict:
    """读取兑换价格、每日体力和新手奖励，金额不接受客户端覆盖。"""
    return read_client_data('''(function()
        local g=require('GameSetting');local r={}
        r.exchange=require('GameCurrencyBuySetting')
        r.fatigue=g.daily_free_physical_strength.value
        r.levels=g.levelup_reward.value
        r.coin_limit=g.coin_max_buy_time.value[1]
        r.fatigue_limit=g.fatigue_max_buy_time.value[1]
        r.noob=require('NoobVersionCfg')[3]
        r.sign={}
        for _,id in ipairs(r.noob.noob_sign) do r.sign[#r.sign+1]=require('SignCfg')[id] end
        return r
    end)()''')


def daily_state(user: dict, now: int | None = None) -> dict:
    """只在跨日时重置每日次数，保留累计签到与成长领奖记录。"""
    now = int(time.time()) if now is None else now
    state = user.setdefault('daily_actions', {})
    if state.get('day') != server_day(now):
        state.update({'day': server_day(now), 'coin_buys': 0, 'fatigue_buys': 0, 'fatigue_claimed': []})
    return state


def newbie_data(user: dict) -> dict:
    """恢复当前新手版本的签到、等级领奖和任务阶段。"""
    state = user.get('newbie', {})
    return {'completed_time': state.get('completed_time', 0), 'max_phase': state.get('max_phase', 1),
        'version_id': 3, 'trigger_time': state.get('trigger_time', user.get('created_at', int(time.time()))),
        'newbie_sign': state.get('sign', {'now_sign_times': 0, 'last_sign_timestamp': 0}),
        'newbie_level_reward': {'received_level_list': state.get('levels', [])},
        'got_pt_id_list': state.get('pt_rewards', [])}


def daily_pushes(user: dict) -> list[tuple]:
    """登录和领取后恢复每日购买次数及体力领取标记。"""
    state = daily_state(user)
    return [(15007, {'left_time_coin': state['coin_buys'], 'left_time_fatigue': state['fatigue_buys']}),
        (12045, {'daily_fatigue_dessert_list': [
            {'type': hour, 'is_got': hour in state['fatigue_claimed']} for hour, _, _ in daily_catalog()['fatigue']]}),
        (59011, newbie_data(user))]


def daily_request(user: dict, command: int, request: dict) -> dict:
    """保存扣款、兑换及领取状态，重复领取返回失败。"""
    now = int(time.time())
    cfg = daily_catalog()
    state = daily_state(user, now)
    rewards = []
    if command in (15012, 15016):
        coin = command == 15012
        if (coin and request['id'] != 2) or (not coin and request['num'] != 1):
            raise ValueError('兑换类型或数量无效')
        field = 'coin_buys' if coin else 'fatigue_buys'
        count = state[field]
        if count >= cfg['coin_limit' if coin else 'fatigue_limit']:
            raise ValueError('今日兑换次数已用完')
        row = cfg['exchange'][count]
        suffix = 'money' if coin else 'fatigue'
        amount = row[f'diamond_to_{suffix}']
        if not coin and user.get('stamina', 240)+amount > 999:
            raise ValueError('体力超过可持有上限')
        spend_items(user, [{'id': 1, 'num': row[f'cost_diamond_to_{suffix}']}])
        rewards = [{'id': 2 if coin else 4, 'num': amount}]
        state[field] += 1
    elif command == 15020:
        num = request['num']
        if num <= 0:
            raise ValueError('兑换数量无效')
        balances = build_currency_balances(user)
        remaining, costs = num, []
        # 国服客户端合并免费、PC/安卓和 iOS 移转之花余额，兑换比例为 1:1。
        for item in (32, 31, 30):
            used = min(remaining, balances[item])
            if used:
                costs.append({'id': item, 'num': used})
                remaining -= used
        if remaining:
            raise ValueError('移转之花不足')
        spend_items(user, costs)
        rewards = [{'id': 1, 'num': num}]
    elif command == 12046:
        hour = request['type']
        row = next((r for r in cfg['fatigue'] if r[0] == hour), None)
        local_seconds = (now+8*3600)%86400
        if local_seconds < refresh_hour()*3600:
            local_seconds += 86400
        if not row or hour in state['fatigue_claimed'] or local_seconds < hour*3600:
            raise ValueError('体力领取时间未到或已领取')
        if user.get('stamina', 240)+row[2] > 999:
            raise ValueError('体力超过可持有上限')
        rewards = [{'id': row[1], 'num': row[2]}]
        state['fatigue_claimed'].append(hour)
    else:
        saved = user.setdefault('newbie', {})
        saved.setdefault('trigger_time', user.get('created_at', now))
        if command in (59002, 59012):
            sign = saved.setdefault('sign', {'now_sign_times': 0, 'last_sign_timestamp': 0})
            if server_day(sign['last_sign_timestamp']) == server_day(now) or sign['now_sign_times'] >= len(cfg['sign']):
                raise ValueError('新手签到已完成或今日已签到')
            reward = cfg['sign'][sign['now_sign_times']]['reward']
            rewards = [{'id': reward[0], 'num': reward[1]}]
            sign['now_sign_times'] += 1
            sign['last_sign_timestamp'] = now
        elif command == 59004:
            level = request['level']
            row = next((r for r in cfg['levels'] if r[0] == level), None)
            claimed = saved.setdefault('levels', [])
            if not row or user.get('level', 80) < level or level in claimed:
                raise ValueError('等级奖励未达成或已领取')
            rewards = [{'id': row[1][0], 'num': row[1][1]}]
            claimed.append(level)
        else:
            index = request['id']
            rows = cfg['noob']['noob_task_progress_reward']
            row = rows[index-1] if 1 <= index <= len(rows) else None
            claimed = saved.setdefault('pt_rewards', [])
            from gameplay_data import client_catalog
            done = sum(bool(user.get('tasks', {}).get(str(c['id']), {}).get('complete_flag'))
                       for c in client_catalog()['tasks'] if c['type'] == cfg['noob']['noob_task_type'])
            if not row or done < row[0] or index in claimed:
                raise ValueError('新手累计任务奖励未达成或已领取')
            rewards = [{'id': row[1][0], 'num': row[1][1]}]
            claimed.append(index)
    grant_rewards(user, rewards)
    return {'result': 0, **({'reward_list': rewards} if command != 12046 else {})}
