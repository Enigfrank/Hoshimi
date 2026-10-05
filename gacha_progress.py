"""探测自选、扣费、共享保底、重复转换、奖励和记录的持久化业务。"""

from copy import deepcopy
import secrets
import time

from account_defaults import unlock_hero
from battle_rewards import grant_rewards, spend_items
from currency_data import DRAW_CURRENCY_ID
from gacha_catalog import draw_catalog, draw_group, pool_details, available_draw_pools
from loadout_storage import servant_data
from server_clock import business_day

DRAW_COMMANDS = {16010, 16012, 16016, 16018, 16020, 16022}
RNG = secrets.SystemRandom()


def draw_state(user: dict) -> dict:
    """每日仅重置当日抽数，保留各保底组、自选、历史和活动奖励进度。"""
    state = user.setdefault('draw', {'groups': {}, 'pools': {}, 'records': {}, 'bonuses': {},
                                    'first_ssr': user.get('account_template') == 'normal', 'newbie_closed': False})
    today = business_day(int(time.time()))
    if state.get('day') != today:
        state.update(day=today, today=0)
    return state


def pool_state(state: dict, pool: dict) -> tuple[dict, dict]:
    """共享保底按探测种类存储，自选和次数限制按具体卡池存储。"""
    group = state['groups'].setdefault(draw_group(pool), {'ssr': 0, 'a': 0, 's_guaranteed': False, 'a_guaranteed': False})
    selected = state['pools'].setdefault(str(pool['id']), {'up': 0, 'up_times': 0, 'is_new': 1, 'total': 0})
    return group, selected


def draw_init(user: dict) -> dict:
    """登录恢复开放池的计数和自选；下发的 up 为实际物品 ID。"""
    state = draw_state(user)
    rows = []
    for pool_id in sorted(available_draw_pools()):
        pool = draw_catalog()['pools'][pool_id]
        group, selected = pool_state(state, pool)
        rows.append({'id': pool_id, 'ssr_draw_times': group['ssr'],
                     'up': selected['up'], 'up_times': selected['up_times'], 'is_new': selected['is_new']})
    return {'draw_info_list': rows, 'today_draw_times': state['today'],
            'first_ssr_draw_flag': state['first_ssr'], 'newbie_choose_draw_flag': state['newbie_closed']}


def bonus_pushes(user: dict) -> list[tuple]:
    """恢复开放探测活动的累计奖励进度。"""
    from activity_data import build_available_activities
    opened = {a['activity_id'] for a in build_available_activities() if a['state'] == 1}
    state = draw_state(user)
    return [(16025, {'activity_id': aid, 'value': state['bonuses'].get(str(aid), 0)})
            for aid in draw_catalog()['bonuses'] if aid in opened]


def get_pool(pool_id: int) -> dict:
    """拒绝未开放或不存在的卡池，客户端不能任意指定历史池。"""
    if pool_id not in available_draw_pools():
        raise ValueError('探测池未开放')
    return draw_catalog()['pools'][pool_id]


def select_up(user: dict, pool: dict, item: int) -> dict:
    """校验自选名单和切换上限；切换不重置保底或歪后保证。"""
    state = draw_state(user)
    _, selected = pool_state(state, pool)
    options = pool['optional_lists']
    if not isinstance(options, list) or item not in options:
        raise ValueError('该角色或钥从不在自选名单')
    if pool['pool_type'] == 8 and state['newbie_closed']:
        raise ValueError('新人定向探测已完成')
    if selected['up'] == item:
        return {'result': 0}
    if pool['pool_change'] and selected['up_times'] >= pool['pool_change']:
        raise ValueError('自选切换次数已用尽')
    selected['up'] = item
    selected['up_times'] += 1
    return {'result': 0}


def draw_cost(pool: dict, request: dict, count: int) -> list[dict]:
    """扣款只使用服务端配置，客户端 id 和数量必须与实际消耗一致。"""
    cost = request['cost']
    expected = (pool['cost_once'][1] * count if count == 1 else
                pool['cost_ten_times'][1] * count // 10 * pool['discount'] // 100)
    options = [(pool['cost_once'][0], expected)]
    activity = pool['cost_once_activity_material'] if count == 1 else pool['cost_ten_times_activity_material']
    if isinstance(activity, list) and len(activity) == 2:
        options.append((activity[0], activity[1]))
    if (cost['id'], cost['num']) not in options or cost.get('convert_from'):
        raise ValueError('探测消耗与配置不一致')
    return [{'id': cost['id'], 'num': cost['num']}]


def roll_item(pool: dict, group: dict, details: dict, state: dict) -> tuple[int, int]:
    """按基础概率及十抽、S 级、UP 保底选择 DrawItemCfg 描述。"""
    kind = pool['pool_type']
    catalog = draw_catalog()
    rates = catalog['rates']
    limit = 90 if kind == 6 else 40 if kind == 8 else 70
    if kind in (1, 5) and state['first_ssr']:
        limit = catalog['rules']['draw_ssr_lucky_num_first_time'][0]
    if kind == 9:
        limit = catalog['rules']['return_draw_ssr_lucky_num_beginner'][0]
    group['ssr'] += 1
    group['a'] += 1
    chance = RNG.random()
    s_rate = rates['FIVE_WEAPON' if kind == 2 else 'S']
    a_rate = rates['FOUR_WEAPON' if kind == 2 else 'A']
    if group['ssr'] >= limit or chance < s_rate:
        rarity = 5
    elif group['a'] >= 10 or chance < s_rate + a_rate:
        rarity = 4
    elif kind != 2 and chance < s_rate + a_rate + rates['B']:
        rarity = 3
    else:
        rarity = 2
    if rarity >= 4:
        prefix = 's' if rarity == 5 else 'a'
        up, others = details[prefix + '_up_item'], details[prefix + '_other_item']
        guaranteed = group[prefix + '_guaranteed'] or (rarity == 5 and kind in (2, 8, 9))
        guaranteed |= rarity == 5 and kind == 6 and group['ssr'] >= limit
        choose_up = bool(up) and (guaranteed or not others or RNG.random() < details[prefix + '_up_probability'] / 100)
        row = RNG.choice(up if choose_up else others or up)
        group[prefix + '_guaranteed'] = bool(up) and not choose_up and not (prefix == 's' and kind == 6)
        group['a'] = 0
        if rarity == 5:
            if kind != 6 or choose_up:
                group['ssr'] = 0
            if kind in (1, 5):
                state['first_ssr'] = False
            if kind == 8:
                state['newbie_closed'] = True
    else:
        candidates = [i for i in details['b_item'] if (catalog['items'][i]['pool_id'] == 301) == (rarity == 3)]
        row = RNG.choice(candidates or details['b_item'])
    return catalog['items'][row]['item_id'], rarity


def award_draw(user: dict, item: int) -> dict:
    """新角色按初始属性解锁，重复角色转情报；钥从逐个保存独立实例。"""
    catalog = draw_catalog()
    result = {'id': item, 'num': 1}
    if str(item) in catalog['heroes']:
        hero = next((h for h in user.get('heroes', []) if h['id'] == item), None)
        rare = catalog['heroes'][str(item)]['rare']
        if hero:
            pieces = catalog['rules']['unlock_hero_need'][rare - 1]
            piece_id = catalog['pieces'][str(item)]
            grant_rewards(user, [{'id': piece_id, 'num': pieces}])
            result = {'id': piece_id, 'num': pieces, 'convert_from': {'id': item, 'num': 1}}
        else:
            unlock_hero(user, item)
        rarity = rare + 2
    else:
        servants = servant_data(user)['servant_list']
        uid = max(user.get('next_servant_uid', 1), max((s['uid'] for s in servants), default=0) + 1)
        servants.append({'uid': uid, 'id': item, 'stage': 1, 'is_locked': 0})
        user['servants'], user['next_servant_uid'] = servants, uid + 1
        rarity = catalog['servants'][str(item)]['starlevel']
    amount = dict(catalog['rules']['currency_for_draw'])[rarity]
    grant_rewards(user, [{'id': DRAW_CURRENCY_ID, 'num': amount}])
    return result


def perform_draw(user: dict, pool: dict, request: dict) -> dict:
    """验证限制后扣款、发奖和记账，调用方在完整协议编码成功后统一保存。"""
    count = request['type']
    if count not in (1, 10):
        raise ValueError('只支持单抽或十连')
    state = draw_state(user)
    group, selected = pool_state(state, pool)
    if state['today'] + count > draw_catalog()['rules']['draw_num_max'][0]:
        raise ValueError('达到每日探测上限')
    if pool['pool_type'] == 5 and selected['total'] + count > 20:
        raise ValueError('新人入职探测次数已用尽')
    if pool['pool_type'] == 8 and state['newbie_closed']:
        raise ValueError('新人定向探测已完成')
    if pool['pool_selected_type'] in (2, 8, 9, 10) and not selected['up']:
        raise ValueError('请先选择定向角色或钥从')
    details = pool_details(pool, selected['up'])
    spend_items(user, draw_cost(pool, request, count))
    results = []
    records = state['records'].setdefault(draw_group(pool), [])
    for _ in range(count):
        if pool['pool_type'] == 5 and selected['total'] == 9 and not selected.get('newbie_a'):
            item = 1037
            group['ssr'] += 1
            group['a'] = 0
        else:
            item, _ = roll_item(pool, group, details, state)
        if pool['pool_type'] == 5 and item == 1037:
            selected['newbie_a'] = True
        result = award_draw(user, item)
        results.append(result)
        records.append({'item': {'id': item, 'num': 1}, 'draw_timestamp': int(time.time())})
        selected['total'] += 1
    state['today'] += count
    opened = {values['activity_id'] for _, values in bonus_pushes(user)}
    for aid, cfg in draw_catalog()['bonuses'].items():
        if aid in opened and pool['id'] in cfg['draw_pool_id']:
            key = str(aid)
            state['bonuses'][key] = state['bonuses'].get(key, 0) + count
    return {'result': 0, 'item': results, 'ssr_draw_times': group['ssr'],
            'first_ssr_draw_flag': state['first_ssr'], 'newbie_choose_draw_flag': state['newbie_closed']}


def draw_request(user: dict, command: int, request: dict) -> dict:
    """处理自选、探测、记录、概率说明、红点和累计奖励领取。"""
    if command == 16022:
        aid = request['activity_id']
        if not any(v['activity_id'] == aid for _, v in bonus_pushes(user)):
            raise ValueError('探测奖励活动未开放')
        cfg = draw_catalog()['bonuses'][aid]
        state = draw_state(user)
        progress = state['bonuses'].get(str(aid), 0)
        count = progress // cfg['need']
        if not count:
            raise ValueError('累计探测次数不足')
        rewards = [{'id': i, 'num': n * count} for i, n in cfg['reward']]
        grant_rewards(user, rewards)
        state['bonuses'][str(aid)] = progress % cfg['need']
        return {'result': 0, 'rewards': rewards}
    pool = get_pool(request['pool'] if command == 16010 else request['pool_id'] if command == 16020 else request['id'])
    state = draw_state(user)
    group, selected = pool_state(state, pool)
    if command == 16016:
        return select_up(user, pool, request['up'])
    if command == 16010:
        return perform_draw(user, pool, request)
    if command == 16018:
        return {'result': 0, 'pool_details': pool_details(pool, selected['up'])}
    if command == 16012:
        return {'result': 0, 'ssr_draw_times': group['ssr'],
                'draw_record_list': deepcopy(state['records'].get(draw_group(pool), [])[-1000:])}
    selected['is_new'] = 0
    return {'result': 0}
