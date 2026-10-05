"""按客户端掉落表生成战斗奖励，并写入账号库存。"""

import random
from functools import lru_cache

from currency_data import build_currency_balances, NATIVE_CURRENCY_IDS, MATERIAL_TOKEN_IDS, CORE_CURRENCY_FIELDS
from gameplay_protocol import read_client_data, decode_message


@lru_cache(maxsize=512)
def drop_config(drop_id: int) -> dict:
    """读取关卡指定的掉落库，不自行添加配置之外的奖励。"""
    return read_client_data(f"require('DropCfg')[{int(drop_id)}] or {{}}")


def roll_drops(config: dict, times: int) -> list[dict]:
    """计算独立概率掉落和权重抽取，合并同一种物品。"""
    totals = {}
    for _ in range(times):
        for item, amount, probability in (config.get('base_drop') or []) + (config.get('random_drop') or []):
            if random.random() * 100 < probability:
                totals[item] = totals.get(item, 0) + amount
        choices = config.get('weight_drop') or []
        if choices:
            for item, amount, _ in random.choices(choices, weights=[c[2] for c in choices],
                                                 k=config.get('weight_drop_count', 0)):
                totals[item] = totals.get(item, 0) + amount
    return [{'id': item, 'num': amount} for item, amount in totals.items()]


@lru_cache(maxsize=1024)
def reward_item(item_id: int) -> dict:
    """读取奖励类型和刻印配置，独立实例不计入材料数量。"""
    return read_client_data(f"(function() local c=require('ItemCfg')[{int(item_id)}] or require('ItemCfg2')[{int(item_id)}]; "
                            f"return {{type=c and c.type or 0,icon=c and c.icon,equip=require('EquipCfg')[{int(item_id)}] "
                            f"or require('EquipCfg2')[{int(item_id)}]}} end)()")


def equipment_data(user: dict) -> dict:
    """合并角色装备与战斗掉落的背包刻印，供登录和结算恢复。"""
    if user.get('equipment_initialized'):
        return {'is_init': 1, 'equip_list': user.get('equipment', [])}
    from proto_bridge import get_bridge
    values = decode_message(13009, get_bridge().encode_sc_13009(user.get('heroes', [])), 'sc')
    values['equip_list'].extend(user.get('equipment', []))
    return values


def grant_rewards(user: dict, rewards: list[dict]) -> None:
    """累计货币与材料余额；既有货币默认余额作为更新起点。"""
    balances = build_currency_balances(user)
    core = CORE_CURRENCY_FIELDS
    for reward in rewards:
        item, amount = reward['id'], reward['num']
        if amount <= 0:
            raise ValueError('奖励数量必须大于零')
        if item in balances:
            value = balances[item] + amount
            user.setdefault('currencies', {})[str(item)] = value
            if item in core:
                user[core[item]] = value
            balances[item] = value
            if item == 12:
                from account_defaults import add_player_exp
                add_player_exp(user, amount)
                balances[4] = user.get('stamina', balances[4])
            if item == 14:
                user['passport_weekly_exp'] = user.get('passport_weekly_exp', 0) + amount
            point_id = {22: 1, 23: 2, 35: 3}.get(item)
            if point_id:
                point = user.setdefault('task_points', {}).setdefault(str(point_id), {'point': 0, 'claimed': []})
                point['point'] += amount
        else:
            cfg = reward_item(item)
            if cfg['type'] in (2, 3):
                hero_id = item if cfg['type'] == 2 else int(cfg['icon'])
                hero = next((h for h in user.get('heroes', []) if h['id'] == hero_id), None)
                if cfg['type'] == 2:
                    if not hero:
                        from account_defaults import unlock_hero
                        unlock_hero(user, hero_id)
                        amount -= 1
                        if not amount:
                            continue
                    pieces = read_client_data(f"require('GameSetting').unlock_hero_need.value[require('HeroCfg')[{hero_id}].rare]")
                    amount *= pieces
                saved = user.setdefault('hero_pieces', {})
                saved[str(hero_id)] = saved.get(str(hero_id), 0) + amount
                continue
            if cfg['type'] == 7:
                inventory = user.setdefault('equipment', [])
                owned_ids = [e['equip_id'] for e in inventory]
                owned_ids.extend(i for h in user.get('heroes', []) for i in h.get('equip_ids', []))
                next_id = max(user.get('next_equip_uid', 1), max(owned_ids, default=0) + 1)
                user['next_equip_uid'] = next_id + amount
                inventory.extend({'equip_id': next_id+i, 'prefab_id': item, 'hero_id': 0,
                                  'exp': 0, 'is_lock': False, 'now_break_level': 0, 'race': 0,
                                  'enchant_slot_list': []} for i in range(amount))
                continue
            if cfg['type'] == 12:
                frames = user.setdefault('unlocked_frames', [])
                if item not in frames:
                    frames.append(item)
                continue
            if cfg['type'] == 9:
                from loadout_storage import servant_data
                inventory = servant_data(user)['servant_list']
                next_id = max(user.get('next_servant_uid', 1), max((s['uid'] for s in inventory), default=0) + 1)
                user['next_servant_uid'] = next_id + amount
                inventory.extend({'uid': next_id+i, 'id': item, 'stage': 1, 'is_locked': 0}
                                 for i in range(amount))
                user['servants'] = inventory
                continue
            decoration_fields = {11: 'icon_list', 13: 'all_sticker_list', 18: 'all_background_list',
                                 21: 'poster_background_list', 22: 'tag_info_list',
                                 23: 'information_background_list', 25: 'all_foreground_list',
                                 26: 'chat_bubble_list', 28: 'game_icon'}
            if cfg['type'] in decoration_fields:
                ids = user.setdefault('unlocked_decorations', {}).setdefault(decoration_fields[cfg['type']], [])
                if item not in ids:
                    ids.append(item)
                continue
            if cfg['type'] == 8:
                skin = read_client_data(f"require('SkinCfg')[{int(item)}] or {{}}")
                hero = next((h for h in user.get('heroes', []) if h['id'] == skin.get('hero')), None)
                owned = user.setdefault('owned_skins', [])
                if item not in owned:
                    owned.append(item)
                if hero and item not in hero['skins']:
                    hero['skins'].append(item)
                continue
            saved = user.setdefault('materials', {})
            saved[str(item)] = saved.get(str(item), 0) + amount


def inventory_pushes(user: dict) -> list[tuple]:
    """结算后同步完整货币和材料库存，避免客户端余额停留在旧值。"""
    balances = build_currency_balances(user)
    materials = {i: balances[i] for i in MATERIAL_TOKEN_IDS}
    materials.update({int(i): n for i, n in user.get('materials', {}).items()})
    result = [(15009, {'last_fatigue_recover_time': 0,
                     'currency_list': [{'id': i, 'num': balances[i]} for i in NATIVE_CURRENCY_IDS]}),
            (17009, {'material_list': [{'id': i, 'num': n, 'time_valid': 0} for i, n in materials.items()]}),
            (13009, equipment_data(user))]
    if user.get('account_template') == 'normal':
        result.extend([(12009, {'user_level': user['level']}),
                       (23009, {'nick': user['nick'], 'total_exp': user['total_exp'],
                                'hero_num': len(user['heroes']), 'plot_progress': user.get('plot_progress', 0),
                                'is_changed_nick': user.get('is_changed_nick', 0),
                                'system_change_nick_times': user.get('system_change_nick_times', 0)})])
    return result


def spend_items(user: dict, costs: list[dict]) -> None:
    """合并并校验全部消耗后扣款，拒绝负数及余额不足。"""
    totals = {}
    for cost in costs:
        if cost['num'] <= 0:
            raise ValueError('消耗数量必须大于零')
        totals[cost['id']] = totals.get(cost['id'], 0) + cost['num']
    balances = build_currency_balances(user)
    for item, amount in totals.items():
        if (balances.get(item, user.get('materials', {}).get(str(item), 0))) < amount:
            raise ValueError('货币或材料不足')
    core = CORE_CURRENCY_FIELDS
    for item, amount in totals.items():
        if item in balances:
            value = balances[item] - amount
            user.setdefault('currencies', {})[str(item)] = value
            if item in core:
                user[core[item]] = value
        else:
            user['materials'][str(item)] -= amount
