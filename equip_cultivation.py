"""刻印强化、分解、洗练与重构的真实库存操作。"""

from copy import deepcopy
from functools import lru_cache
import random

from battle_rewards import equipment_data, grant_rewards, reward_item, spend_items
from gameplay_protocol import read_client_data

EQUIP_COMMANDS = {13014, 13022, 13024, 13028, 13030, 13032, 13034, 13044,
                  13046, 13052, 13058, 13060}


@lru_cache(maxsize=1)
def cultivation_catalog() -> dict:
    """一次读取消耗、经验、洗练池与神系配置，避免每次操作遍历 Lua。"""
    return read_client_data('''(function()
        local r={settings={},materials={},exp={},pools={},races={}}
        local c=require('GameSetting')
        for _,k in ipairs({'equip_strengthen_gold_cost','equip_break_user_level','base_exp_equip_star',
            'equip_exp_props_id_list','equip_break_cost_return','equip_resolve_num','equip_enchant_cost',
            'equip_enchant_lock_cost','equip_enchant_save_num','equip_enchant_directional_cost',
            'equip_reset_cost','equip_hero_reset_cost','equip_inherit_cost'}) do r.settings[k]=c[k].value end
        for _,name in ipairs({'EquipMaterialCfg','EquipExpCfg','EquipSkillPoolCfg'}) do
            c=require(name)
            local target=name=='EquipMaterialCfg' and r.materials or name=='EquipExpCfg' and r.exp or r.pools
            for _,id in ipairs(c.all) do target[tostring(id)]=c[id] end
        end
        r.races=require('RaceEffectCfg').all
        return r
    end)()''')


def material_cost(config_id: int) -> list[dict]:
    """从客户端成本表转换扣款条目，不接受客户端声明的价格。"""
    return [{'id': i, 'num': n} for i, n in cultivation_catalog()['materials'][str(config_id)]['item_list'] if n]


def equip_level(equip: dict) -> int:
    """依据累计经验和当前突破上限读取刻印等级。"""
    cfg = reward_item(equip['prefab_id'])['equip']
    maximum = cfg['max_level'][equip['now_break_level']]
    exp = cultivation_catalog()['exp']
    return max(i for i in range(1, maximum+1) if exp[str(i)][f"exp_sum_{cfg['starlevel']}"] <= equip['exp'])


def removable_equips(user: dict, ids: list, forbidden: int = 0) -> list[dict]:
    """消耗刻印前校验拥有、锁定、装备占用与重复实例。"""
    if len(ids) != len(set(ids)) or forbidden in ids:
        raise ValueError('消耗刻印重复或包含目标刻印')
    inventory = {e['equip_id']: e for e in user['equipment']}
    worn = {uid for h in user['heroes'] for uid in h.get('equip_ids', []) if uid}
    rows = [inventory.get(uid) for uid in ids]
    if any(e is None or e['is_lock'] or e['equip_id'] in worn for e in rows):
        raise ValueError('消耗刻印未拥有、已锁定或正在装备')
    return rows


def remove_equips(user: dict, ids: list) -> None:
    """移除已校验实例，并清除保存方案中的失效引用。"""
    removed = set(ids)
    user['equipment'] = [e for e in user['equipment'] if e['equip_id'] not in removed]
    for proposal in user.get('equip_proposals', []):
        for row in proposal['equip']:
            if row['equip_id'] in removed:
                row['equip_id'] = 0


def exp_materials(amount: int) -> list[dict]:
    """按客户端经验材料面值转换多余经验或分解所得。"""
    result = []
    ids = cultivation_catalog()['settings']['equip_exp_props_id_list']
    for item in reversed(ids):
        value = read_client_data(f"require('ItemCfg')[{item}].param[1]")
        count, amount = divmod(amount, value)
        if count:
            result.append({'id': item, 'num': count})
    return result


def strengthen(user: dict, equip: dict, request: dict, one_key: bool) -> dict:
    """扣除真实强化材料与突破成本，保存经验并返还超出上限的材料。"""
    catalog = cultivation_catalog()
    settings = catalog['settings']
    cfg = reward_item(equip['prefab_id'])['equip']
    steps = request['break_times'] if one_key else 0
    current = equip['now_break_level']
    if steps < 0 or current+steps > cfg['break_times_max']:
        raise ValueError('刻印突破次数无效')
    maximum = cfg['max_level'][current+steps]
    target = request['target_level'] if one_key else maximum
    if not equip_level(equip) < target <= maximum:
        raise ValueError('刻印强化目标等级无效')
    consumed = removable_equips(user, request['equip_list'], equip['equip_id'])
    gain = sum(int(e['exp']*0.8)+settings['base_exp_equip_star'][reward_item(e['prefab_id'])['equip']['starlevel']-1]
               for e in consumed)
    costs = []
    for row in request['mat_list']:
        cfg_item = read_client_data(f"require('ItemCfg')[{int(row['id'])}] or {{}}")
        if cfg_item.get('sub_type') != 608 or row['num'] <= 0:
            raise ValueError('刻印强化材料无效')
        gain += cfg_item['param'][0]*row['num']
        costs.append({'id': row['id'], 'num': row['num']})
    limit = catalog['exp'][str(target)][f"exp_sum_{cfg['starlevel']}"]
    needed = limit-equip['exp']
    if gain <= 0 or (one_key and gain < needed):
        raise ValueError('刻印强化经验不足')
    applied = min(gain, needed)
    costs.append({'id': 2, 'num': int(applied*settings['equip_strengthen_gold_cost'][0])})
    for index in range(current, current+steps):
        if user.get('level', 80) < settings['equip_break_user_level'][index]:
            raise ValueError('玩家等级不足')
        costs.extend(material_cost(cfg['break_cost'][index]))
    spend_items(user, costs)
    equip['exp'] += applied
    equip['now_break_level'] += steps
    remove_equips(user, request['equip_list'])
    returned = exp_materials(gain-applied)
    grant_rewards(user, returned)
    return {'result': 0, 'mat_list': returned}


def equip_request(user: dict, command: int, request: dict) -> dict:
    """处理刻印写协议，预览结果同样保存，重启后可以确认或放弃。"""
    if not user.get('equipment_initialized'):
        user['equipment'] = deepcopy(equipment_data(user)['equip_list'])
        user['equipment_initialized'] = True
    settings = cultivation_catalog()['settings']
    if command == 13024:
        ids = request['equip_id_list']
        if not ids:
            raise ValueError('刻印分解列表为空')
        rows = removable_equips(user, ids)
        rewards = []
        for row in rows:
            cfg = reward_item(row['prefab_id'])['equip']
            rewards.extend(exp_materials(int(row['exp']*0.8)+settings['base_exp_equip_star'][cfg['starlevel']-1]))
            returns = settings['equip_break_cost_return'][cfg['starlevel']-1]
            for cost_id in list(returns)[:row['now_break_level']]:
                rewards.extend(c for c in material_cost(cost_id) if c['id'] != 2)
            if cfg['starlevel'] > 4:
                item, num = settings['equip_resolve_num'][cfg['starlevel']-5]
                rewards.append({'id': item, 'num': num})
        remove_equips(user, ids)
        grant_rewards(user, rewards)
        return {'result': 0, 'return_mat_list': rewards}
    equip = next((e for e in user['equipment'] if e['equip_id'] == request.get('equip_id', request.get('new_equip_id'))), None)
    if not equip:
        raise ValueError('刻印未拥有')
    cfg = reward_item(equip['prefab_id'])['equip']
    response = {'result': 0}
    if command in (13014, 13058):
        return strengthen(user, equip, request, command == 13058)
    if command == 13022:
        index = equip['now_break_level']
        if index >= cfg['break_times_max'] or equip_level(equip) != cfg['max_level'][index]:
            raise ValueError('刻印尚未达到突破等级或已满突破')
        if user.get('level', 80) < settings['equip_break_user_level'][index]:
            raise ValueError('玩家等级不足')
        spend_items(user, material_cost(cfg['break_cost'][index]))
        equip['now_break_level'] += 1
    elif command in (13032, 13034, 13046):
        if command == 13034:
            if not equip.get('race_preview'):
                raise ValueError('没有待确认的神系')
            if request['confirm']:
                equip['race'] = equip['race_preview']
            equip['race_preview'] = 0
        else:
            race = random.choice(cultivation_catalog()['races'])
            if command == 13046:
                if request['hero_id'] not in {h['id'] for h in user['heroes']}:
                    raise ValueError('重构角色未拥有')
                race = request['hero_id']
            key = 'equip_reset_cost' if command == 13032 else 'equip_hero_reset_cost'
            spend_items(user, material_cost(settings[key][0]))
            if command == 13032:
                equip['race_preview'] = race
                response['race_preview'] = race
            else:
                equip['race'] = race
                equip['is_lock'] = True
    elif command == 13052:
        target = reward_item(request['inherit_equip_prefab_id'])['equip']
        if not target or target['pos'] != cfg['pos'] or target['starlevel'] != cfg['starlevel']:
            raise ValueError('刻印继承槽位或星级不匹配')
        kind = read_client_data(f"require('EquipSuitCfg')[{target['suit']}].inherit_cost_type")
        if kind not in (1, 2):
            raise ValueError('刻印不支持继承')
        spend_items(user, material_cost(settings['equip_inherit_cost'][kind-1]))
        equip['prefab_id'] = target['id']
    else:
        index = request['enchant_slot_id']
        if not 1 <= index <= cfg['slot_num'] or equip_level(equip) < cfg['slot_open_level'][index-1]:
            raise ValueError('刻印洗练槽位尚未解锁')
        slots = equip['enchant_slot_list']
        slot = next((s for s in slots if s['id'] == index), None)
        if slot is None:
            slot = {'id': index, 'effect_list': [], 'preview_list': []}
            slots.append(slot)
        previews = slot.setdefault('preview_list', [])
        if command == 13044:
            previews.clear()
        elif command == 13030:
            selected = request['preview_index']
            if not 1 <= selected <= len(previews):
                raise ValueError('洗练预览不存在')
            preview = previews.pop(selected-1)
            if request['confirm']:
                slot['effect_list'] = deepcopy(preview['effect_list'])
        elif command == 13060:
            skill = read_client_data(f"require('EquipSkillCfg')[{int(request['id'])}] or {{}}")
            seq = request['seq']
            if not 1 <= seq <= min(2, len(slot['effect_list'])+1) or not skill:
                raise ValueError('定向洗练技能或位置无效')
            allowed = read_client_data("require('EquipSkillCfg').get_id_list_by_skill_type[require('EquipConst').EQUIP_ATTRIBUTE_TYPE.ENCHANT]")
            if request['id'] not in allowed:
                raise ValueError('技能不属于洗练池')
            spend_items(user, material_cost(settings['equip_enchant_directional_cost'][0]))
            effect = {'id': request['id'], 'level': 1}
            if seq == len(slot['effect_list'])+1:
                slot['effect_list'].append(effect)
            else:
                slot['effect_list'][seq-1] = effect
        elif command == 13028:
            if len(previews) >= settings['equip_enchant_save_num'][0]:
                raise ValueError('洗练预览已满')
            lock = request['lock_type']
            if lock not in (0, 1, 2) or (lock and len(slot['effect_list']) < lock):
                raise ValueError('洗练锁定位置无效')
            costs = None
            ids = settings['equip_enchant_lock_cost'] if lock else settings['equip_enchant_cost']
            for cost_id in ids:
                rows = material_cost(cost_id)
                material = next((r for r in rows if r['id'] != 2), None)
                pool = read_client_data(f"require('ItemCfg')[{material['id']}].param[1]") if material else None
                if pool == request['pool_id']:
                    costs = rows
                    break
            choices = [p for p in cultivation_catalog()['pools'].values() if p['pool_id'] == request['pool_id']]
            if costs is None or not choices:
                raise ValueError('洗练池无效')
            if lock:
                locked = slot['effect_list'][lock-1]
                choices = [p for p in choices if len(p['skill_id']) >= lock and
                           p['skill_id'][lock-1] == [locked['id'], locked['level']]]
                if not choices:
                    raise ValueError('当前洗练池没有匹配锁定技能的结果')
            picked = random.choices(choices, weights=[p['weight'] for p in choices])[0]
            effects = [{'id': i, 'level': n} for i, n in picked['skill_id']]
            spend_items(user, costs)
            preview = {'effect_list': effects}
            previews.append(preview)
            response['enchant_preview'] = deepcopy(preview)
    return response
