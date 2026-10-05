"""钥从精炼、唤名和分解的独立实例持久化。"""

from functools import lru_cache

from battle_rewards import grant_rewards, spend_items
from gameplay_protocol import read_client_data
from loadout_storage import servant_data

SERVANT_COMMANDS = {46012, 46030, 46032}


@lru_cache(maxsize=1)
def servant_catalog() -> dict:
    """读取钥从精炼成本、唤名成本和分解返还表。"""
    return read_client_data('''(function()
        local c=require('GameSetting'); local r={}
        for _,k in ipairs({'weapon_promote_max','weapon_servant_gold_cost','weapon_promote_cost_exclusive',
            'weapon_promote_cost','exclusive_weapon_servant_cost','weapon_servant_break_cost_return'}) do
            r[k]=c[k].value
        end
        return r
    end)()''')


@lru_cache(maxsize=256)
def servant_config(item: int) -> dict:
    """获取钥从种类、神系与专属归属，拒绝不存在的配置。"""
    return read_client_data(f'''(function()
        local c=require('WeaponServantCfg')[{int(item)}]; if not c then return {{}} end
        local e=c.effect[1] and require('WeaponEffectCfg')[c.effect[1]]
        return {{id=c.id,race=c.race,starlevel=c.starlevel,type=c.type,
            hero_id=e and e.spec_char and e.spec_char[1] or 0}}
    end)()''')


def consume_servants(user: dict, inventory: list, ids: list) -> list:
    """消耗前校验锁定与装备关系，禁止重复消耗同一钥从。"""
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('钥从消耗列表为空或重复')
    worn = {h.get('servant_uid', h['id']) for h in user['heroes']}
    by_id = {s['uid']: s for s in inventory}
    rows = [by_id.get(uid) for uid in ids]
    if any(s is None or s['is_locked'] or s['uid'] in worn for s in rows):
        raise ValueError('消耗钥从未拥有、已锁定或正在装备')
    return rows


def servant_request(user: dict, command: int, request: dict) -> dict:
    """执行精炼、唤名或分解，并保存库存、精炼等级和装备引用。"""
    inventory = servant_data(user)['servant_list']
    catalog = servant_catalog()
    response = {'result': 0}
    if command == 46012:
        target = next((s for s in inventory if s['uid'] == request['uid']), None)
        if not target:
            raise ValueError('钥从未拥有')
        cfg = servant_config(target['id'])
        star, stage = cfg['starlevel'], target['stage']
        if cfg['type'] == 3 or stage > catalog['weapon_promote_max'][star-1]:
            raise ValueError('钥从不能继续精炼')
        costs = [{'id': 2, 'num': catalog['weapon_servant_gold_cost'][star-1][stage-1]}]
        removed = []
        if request['refined_type'] == 0:
            if request['cost_uid'] == target['uid']:
                raise ValueError('不能消耗目标钥从')
            rows = consume_servants(user, inventory, [request['cost_uid']])
            if rows[0]['id'] != target['id']:
                raise ValueError('精炼须消耗同名钥从')
            removed = [request['cost_uid']]
        elif request['refined_type'] == 1:
            material = catalog['weapon_promote_cost_exclusive'] if cfg['hero_id'] else catalog['weapon_promote_cost'][star-4]
            costs.append({'id': material[0], 'num': material[1]})
        else:
            raise ValueError('钥从精炼类型无效')
        spend_items(user, costs)
        target['stage'] += 1
        inventory = [s for s in inventory if s['uid'] not in removed]
    elif command == 46032:
        ids = request['servant_list']
        rows = consume_servants(user, inventory, ids)
        rewards = []
        for row in rows:
            star = servant_config(row['id'])['starlevel']
            rewards.extend({'id': i, 'num': n} for i, n in catalog['weapon_servant_break_cost_return'][star-1])
        inventory = [s for s in inventory if s['uid'] not in ids]
        grant_rewards(user, rewards)
        response['return_list'] = rewards
    else:
        cfg = servant_config(request['servant_id'])
        if not cfg or not cfg['hero_id']:
            raise ValueError('唤名目标不是专属钥从')
        cost = next((c[1] for c in catalog['exclusive_weapon_servant_cost'] if c[0] == cfg['race']), None)
        ids = request['cost_uid_list']
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('唤名消耗列表为空或重复')
        by_id = {s['uid']: s for s in inventory}
        rows = [by_id.get(uid) for uid in ids]
        if any(s is None for s in rows):
            raise ValueError('唤名消耗钥从未拥有')
        if not cost or len(rows) != cost[0][1] or any(s['id'] != cost[0][0] or s['stage'] != 1 for s in rows):
            raise ValueError('唤名消耗钥从不匹配')
        worn = [h for h in user['heroes'] if h.get('servant_uid', h['id']) in ids]
        if len(worn) > 1:
            raise ValueError('唤名不能同时替换多个角色的钥从')
        spend_items(user, [{'id': i, 'num': n} for i, n in cost[1:]])
        uid = max(user.get('next_servant_uid', 1), max((s['uid'] for s in inventory), default=0)+1)
        user['next_servant_uid'] = uid+1
        inventory = [s for s in inventory if s['uid'] not in ids]
        # 客户端唤名会继承首个胚子的锁定，以及被消耗胚子的装备关系。
        inventory.append({'uid': uid, 'id': cfg['id'], 'stage': 1, 'is_locked': rows[0]['is_locked']})
        for hero in worn:
            hero['servant_uid'] = uid
        response['servant_uid'] = uid
    user['servants'] = inventory
    return response
