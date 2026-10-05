"""活动皮肤有限奖池、十抽保底、翻牌与奖励的账号存档。"""

import secrets

from battle_rewards import grant_rewards, spend_items
from currency_data import build_currency_balances
from skin_draw_catalog import skin_catalog, skin_pools, pool_main, skin_activities

SKIN_DRAW_COMMANDS = {68152, 68156, 68162, 68186}
RNG = secrets.SystemRandom()


def skin_state(user: dict, pool: dict) -> dict:
    """剩余奖品、核心保底和翻牌轮次随账号保存，不因登录重新填满。"""
    rows = [d for d in skin_catalog()['drops'].values() if d['pool_id'] == pool['pool_id']]
    return user.setdefault('skin_draw', {}).setdefault(str(pool['pool_id']), {
        'remaining': {str(d['id']): d['total'] for d in rows}, 'pity': 0,
        'cards': [], 'target': 0, 'round_done': True, 'records': []})


def remaining_drops(state: dict, pool: dict) -> list[dict]:
    """场景扩展池在基础场景获得前锁定第二阶段。"""
    catalog = skin_catalog()
    rows = [d for d in catalog['drops'].values() if d['pool_id'] == pool['pool_id']]
    locked = any(d['pool_stage'] == 1 and state['remaining'][str(d['id'])] > 0
                 and catalog['items'][str(d['reward'][0][0])]['type'] == 21 for d in rows)
    return [d for d in rows if state['remaining'][str(d['id'])] > 0
            and (d['pool_stage'] == 1 or not locked)]


def weighted_drop(state: dict, drops: list[dict]) -> dict:
    """每个奖品使用剩余数量乘公开权重；普通奖品按剩余份数抽取。"""
    return RNG.choices(drops, weights=[state['remaining'][str(d['id'])] * d['weight'] for d in drops], k=1)[0]


def prepare_round(state: dict, pool: dict) -> None:
    """翻牌每轮随机指定一个核心保底，已有未完成轮次原样恢复。"""
    if not state['round_done']:
        return
    rows = remaining_drops(state, pool)
    core = [d for d in rows if d['minimum_guarantee'] == 2]
    state['target'] = weighted_drop(state, core)['id'] if core else 0
    state['cards'] = [0] * min(10, sum(state['remaining'][str(d['id'])] for d in rows))
    state['round_done'] = False


def owns_unique(user: dict, item: dict) -> bool:
    """校验皮肤、场景、头像框和表情的永久拥有状态，供重复兑换使用。"""
    iid, kind = item['id'], item['type']
    if kind == 8:
        return iid in user.get('owned_skins', []) or any(iid in h['skins'] for h in user.get('heroes', []))
    if kind == 12:
        from profile_data import profile_data
        return iid in {r['id'] for r in profile_data(user)['icon_frame_list']}
    if kind == 21:
        from profile_data import profile_data
        return iid in {r['id'] for r in profile_data(user)['poster_background_list']}
    if kind == 20:
        return user.get('materials', {}).get(str(iid), 0) > 0
    return False


def award_skin_drop(user: dict, drop: dict) -> None:
    """直开固定皮肤礼包，已有永久奖品按客户端配置兑换，保留可选材料礼包。"""
    catalog = skin_catalog()
    rewards = []
    for iid, amount in drop['reward']:
        item = catalog['items'][str(iid)]
        contents = item['param'] if item['type'] == 5 and item['sub_type'] == 501 else [[iid, 1]]
        for target, num in contents:
            cfg = catalog['items'][str(target)]
            if owns_unique(user, cfg) and cfg['exchange']:
                rewards.extend({'id': i, 'num': n * num * amount} for i, n in cfg['exchange'])
            else:
                rewards.append({'id': target, 'num': num * amount})
                main = pool_main(drop['pool_id'])
                if cfg['type'] == 8 and main.get('story_item', 0) > 0:
                    pending = user.setdefault('skin_memory_pending', [])
                    if target not in pending and target not in user.get('skin_memory_claimed', []):
                        pending.append(target)
    grant_rewards(user, rewards)


def skin_pushes(user: dict, pool_ids: set[int] | None = None) -> list[tuple]:
    """初始化及更新真实剩余数量、翻牌与剧情，供客户端刷新页面。"""
    result = []
    for pool in skin_pools():
        if pool_ids is not None and pool['pool_id'] not in pool_ids:
            continue
        state = skin_state(user, pool)
        values = {'activity_id': pool['activity_id'][0],
                  'info': [{'drop_id': int(i), 'num': n} for i, n in state['remaining'].items()]}
        oath = pool_main(pool['pool_id'])['oath']
        if oath:
            if not state['cards']:
                prepare_round(state, pool)
            values['draw_info2'] = {'last_drop': state['target'], 'already_drop': state['cards']}
        result.append((68185 if oath else 68151, values))
    if pool_ids is None:
        opened = {a['activity_id'] for a in skin_activities()}
        for cfg in skin_catalog()['stories']:
            if cfg['activity_id'] in opened:
                result.append((68161, {'activity_id': cfg['activity_id'], 'story_stage': 1,
                                      'finished_story': [i for i in user.get('read_stories', [])
                                                         if i == cfg['story_id']]}))
    if user.get('skin_memory_pending'):
        result.append((68155, {'skin_id': user['skin_memory_pending']}))
    return result


def skin_request(user: dict, command: int, request: dict) -> dict:
    """扣除实际票券，发奖并写入奖池；调用方完成编码后原子保存整个账号。"""
    catalog = skin_catalog()
    if command == 68156:
        skin_id = request['skin_id']
        main = next((m for m in catalog['mains'] if m.get('story_item', 0) > 0
                     and any(skin_id == i or (catalog['items'][str(i)]['type'] == 5
                                 and [skin_id, 1] in catalog['items'][str(i)]['param'])
                             for d in catalog['drops'].values() if d['pool_id'] in m['poolList']
                             for i, _ in d['reward'])), None)
        if not main or skin_id not in user.get('skin_memory_pending', []) or skin_id in user.get('skin_memory_claimed', []):
            raise ValueError('回忆奖励未解锁或已领取')
        grant_rewards(user, [{'id': main['story_item'], 'num': 1}])
        user.setdefault('skin_memory_claimed', []).append(skin_id)
        user['skin_memory_pending'].remove(skin_id)
        return {'result': 0}
    if command == 68162:
        if not any(c['activity_id'] == request['activity_id'] and c['story_id'] == request['story_id']
                   for c in catalog['stories'] if c['activity_id'] in {a['activity_id'] for a in skin_activities()}):
            raise ValueError('皮肤剧情未开放')
        if request['story_id'] not in user.setdefault('read_stories', []):
            user['read_stories'].append(request['story_id'])
        return {'result': 0}
    pool = next((p for p in skin_pools() if p['pool_id'] == request['pool_id']
                 and request['activity_id'] in p['activity_id']), None)
    if not pool or pool_main(pool['pool_id'])['oath'] != (command == 68186):
        raise ValueError('皮肤奖池或抽奖方式不匹配')
    state = skin_state(user, pool)
    oath = command == 68186
    if oath:
        prepare_round(state, pool)
        index = request['card_index']
        if index < 0 or index > len(state['cards']) or (index and state['cards'][index - 1]):
            raise ValueError('翻牌位置无效或已翻开')
        positions = [index] if index else [i for i, v in enumerate(state['cards'], 1) if not v]
        balance = build_currency_balances(user).get(pool['cost_once'][0], user.get('materials', {}).get(str(pool['cost_once'][0]), 0))
        positions = positions[:balance // pool['cost_once'][1]]
        count = len(positions)
    else:
        count = request['drop_type']
        if count not in (1, 10):
            raise ValueError('皮肤抽奖只支持单抽或十连')
    if count <= 0 or sum(state['remaining'].values()) < count:
        raise ValueError('抽奖券不足或奖池数量不足')
    results = []
    for turn in range(count):
        rows = remaining_drops(state, pool)
        core = [d for d in rows if d['minimum_guarantee'] == 2]
        others = [d for d in rows if d['minimum_guarantee'] != 2]
        state['pity'] += 1
        if oath and state['target']:
            target = catalog['drops'][state['target']]
            guarantee = sum(bool(i) for i in state['cards']) >= len(state['cards']) - 1
            drop = target if guarantee or RNG.random() < 0.01 or not others else weighted_drop(state, others)
        else:
            drop = weighted_drop(state, core if core and (state['pity'] >= 10 or RNG.random() < 0.01 or not others) else others or core)
        spend_items(user, [{'id': pool['cost_once'][0], 'num': pool['cost_once'][1]}])
        award_skin_drop(user, drop)
        state['remaining'][str(drop['id'])] -= 1
        if drop['minimum_guarantee'] == 2:
            state['pity'] = 0
        state['records'].append(drop['id'])
        if oath:
            state['cards'][positions[turn] - 1] = drop['id']
            results.append({'card_index': positions[turn], 'drop_id': drop['id']})
            if drop['id'] == state['target'] or all(state['cards']):
                state['round_done'] = True
                break
        else:
            results.append(drop['id'])
    return {'result': 0, 'drop_list': results}
