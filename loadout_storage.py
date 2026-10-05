"""钥从装备、刻印方案与芯片选择的账号存档。"""

from copy import deepcopy
from functools import lru_cache

from battle_rewards import equipment_data, spend_items
from gameplay_protocol import decode_message, read_client_data
from proto_bridge import get_bridge

LOADOUT_COMMANDS = {46014, 46020, 13036, 13038, 13040, 13042,
                    50002, 50008, 50010, 50012, 50018}


def servant_data(user: dict) -> dict:
    """恢复独立钥从库存，装备关系由角色的 servant_uid 保存。"""
    if 'servants' in user:
        return {'servant_list': deepcopy(user['servants'])}
    return decode_message(46011, get_bridge().encode_sc_46011(user.get('heroes', [])), 'sc')


def chip_data(user: dict) -> dict:
    """登录恢复解锁芯片、芯片方案与角色芯片槽位。"""
    return deepcopy(user.get('chips', {}))


@lru_cache(maxsize=256)
def chip_config(chip_id: int) -> dict:
    """读取客户端有效芯片及其成本、归属和槽位。"""
    return read_client_data(f"require('ChipCfg')[{int(chip_id)}] or {{}}")


def validate_equips(user: dict, rows: list[dict]) -> None:
    """保存方案前校验刻印拥有关系、重复和槽位。"""
    inventory = {e['equip_id']: e for e in equipment_data(user)['equip_list']}
    positions, ids = set(), set()
    for row in rows:
        position, uid = row['pos'], row['equip_id']
        if not 1 <= position <= 6 or position in positions or (uid and uid in ids):
            raise ValueError('刻印方案槽位或实例重复')
        positions.add(position)
        if uid:
            equip = inventory.get(uid)
            if not equip:
                raise ValueError('方案刻印未拥有')
            from battle_rewards import reward_item
            if reward_item(equip['prefab_id'])['equip']['pos'] != position:
                raise ValueError('方案刻印槽位不匹配')
            ids.add(uid)


def loadout_request(user: dict, command: int, request: dict) -> dict:
    """校验后保存钥从、刻印方案或芯片，并返回真实协议结果。"""
    response = {'result': 0}
    if command in (46014, 46020):
        inventory = servant_data(user)['servant_list']
        uid = request.get('uid', request.get('servant_id', 0))
        servant = next((s for s in inventory if s['uid'] == uid), None)
        if command == 46014:
            if not servant or request['is_lock'] not in (0, 1):
                raise ValueError('钥从或锁定状态无效')
            servant['is_locked'] = request['is_lock']
        else:
            hero = next((h for h in user['heroes'] if h['id'] == request['hero_id']), None)
            if not hero or (uid and not servant):
                raise ValueError('角色或钥从未拥有')
            if servant:
                race = read_client_data(f"require('WeaponServantCfg')[{servant['id']}].race")
                hero_race = read_client_data(f"require('HeroCfg')[{hero['id']}].race")
                if race != hero_race:
                    raise ValueError('钥从神系不匹配')
                for owned in user['heroes']:
                    if owned.get('servant_uid', owned['id']) == uid:
                        owned['servant_uid'] = 0
            hero['servant_uid'] = uid
        user['servants'] = inventory
    elif command in (13036, 13038, 13040, 13042):
        proposals = user.setdefault('equip_proposals', [])
        if command in (13036, 13042):
            limit = read_client_data("require('GameSetting').equip_proposal_num_max.value[1]")
            if len(proposals) >= limit or not request['proposal_name'].strip():
                raise ValueError('方案数量或名称无效')
            if command == 13036:
                hero = next((h for h in user['heroes'] if h['id'] == request['hero_id']), None)
                if not hero:
                    raise ValueError('方案角色未拥有')
                rows = [{'pos': pos, 'equip_id': uid} for pos, uid in enumerate(hero['equip_ids'], 1)]
            else:
                rows = deepcopy(request['equip'])
            validate_equips(user, rows)
            uid = user.get('next_equip_proposal', 1)
            user['next_equip_proposal'] = uid + 1
            proposals.append({'id': uid, 'name': request['proposal_name'], 'equip': rows})
            response['proposal_id'] = uid
        else:
            proposal = next((p for p in proposals if p['id'] == request['proposal_id']), None)
            if not proposal:
                raise ValueError('刻印方案不存在')
            if command == 13040:
                proposals.remove(proposal)
            else:
                if not request['proposal_name'].strip():
                    raise ValueError('方案名称无效')
                proposal['name'] = request['proposal_name']
    else:
        chips = user.setdefault('chips', {})
        if command == 50002:
            cfg = chip_config(request['id'])
            if not cfg:
                raise ValueError('芯片不存在')
            field = {1: 'unlock_kernel_chip', 2: 'unlock_secondary_chip',
                     3: 'unlock_hero_chip', 4: 'unlock_reviser_chip'}[cfg['type_id']]
            ids = chips.setdefault(field, [])
            if cfg['id'] in ids:
                raise ValueError('芯片已经解锁')
            costs = cfg.get('cost_condition') or []
            spend_items(user, [{'id': i, 'num': n} for i, n in costs])
            ids.append(cfg['id'])
        elif command == 50018:
            hero = request['hero_id']
            if hero not in {h['id'] for h in user['heroes']} or not 1 <= request['slot_id'] <= 4:
                raise ValueError('角色芯片槽位无效')
            chip = request['secondary']
            cfg = chip_config(chip) if chip else {}
            if chip and (chip not in chips.get('unlock_hero_chip', []) or cfg.get('spec_char') != hero
                         or cfg.get('role_type_id') != request['slot_id']):
                raise ValueError('角色芯片未解锁或槽位不符')
            rows = chips.setdefault('hero_chip_state', [])
            row = next((r for r in rows if r['hero_id'] == hero), None)
            if row is None:
                row = {'hero_id': hero, 'secondary': [0]*4}
                rows.append(row)
            row['secondary'][request['slot_id']-1] = chip
        else:
            proposals = chips.setdefault('proposals', [])
            proposal = next((p for p in proposals if p['id'] == request['id']), None)
            if command == 50008:
                ids = request['secondary']
                if len(set(ids)) != len(ids) or any(i not in chips.get('unlock_secondary_chip', []) for i in ids):
                    raise ValueError('方案芯片未解锁或重复')
                if not request['name'].strip() or request['id'] <= 0:
                    raise ValueError('芯片方案编号或名称无效')
                if proposal:
                    proposals.remove(proposal)
                proposals.append(deepcopy(request))
            elif not proposal:
                raise ValueError('芯片方案不存在')
            elif command == 50010:
                proposals.remove(proposal)
            elif command == 50012:
                if not request['name'].strip():
                    raise ValueError('芯片方案名称无效')
                proposal['name'] = request['name']
    return response
