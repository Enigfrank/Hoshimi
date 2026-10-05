"""挑战奖励、重置和难度选择的持久化。"""

from copy import deepcopy

from battle_progress import progress
from battle_rewards import drop_config, roll_drops, grant_rewards
from challenge_data import challenge_catalog

CHALLENGE_COMMANDS = {44012, 44024, 44026, 44028, 45004, 45006, 45104,
                      45108, 45110, 55002, 55004, 55006}


def challenge_request(user: dict, command: int, request: dict) -> dict:
    """按真实通关记录领取一次奖励，重置保留已经领取的奖励标记。"""
    catalog = challenge_catalog()
    rewards = []
    response = {'result': 0}
    if command == 44012:
        difficulty = user.get('mythic_difficulty', 1)
        cfg = next((c for c in catalog['mythic'] if c['id'] == difficulty), None)
        star = request['star']
        claimed = user.setdefault('mythic_star_rewards', {}).setdefault(str(difficulty), [])
        if not cfg or not 1 <= star <= len(cfg['star_reward_list']) or star in claimed:
            raise ValueError('黑区奖励无效或已领取')
        if len(progress(user, 11, cfg['main_partition']).get('stars', [])) < star:
            raise ValueError('主分区星数不足')
        rewards = roll_drops(drop_config(cfg['star_reward_list'][star-1]), 1)
        claimed.append(star)
        response['item_list'] = rewards
    elif command in (44024, 44026, 44028):
        difficulty = request.get('difficulty_id', user.get('mythic_final_difficulty', 1))
        cfg = next((c for c in catalog['final'] if c['id'] == difficulty), None)
        if not cfg:
            raise ValueError('终末黑区难度无效')
        if command == 44024:
            user['mythic_final_difficulty'] = difficulty
        elif command == 44026:
            user.setdefault('mythic_final_runs', {}).pop(str(difficulty), None)
        else:
            claimed = user.setdefault('mythic_final_rewards', [])
            if difficulty in claimed or difficulty not in user.get('mythic_final_cleared', []):
                raise ValueError('终末黑区未通关或已领取奖励')
            rewards = [{'id': i, 'num': n} for i, n in cfg['reward_list']]
            claimed.append(difficulty)
            response['item_list'] = rewards
    elif command in (45004, 45006):
        area = next(c for c in catalog['boss'] if c['range_id'] == 4)
        groups = area['boss_list'][:area['boss_nums']]
        if command == 45006:
            if request['group_id'] not in groups:
                raise ValueError('梦境分组不存在')
            for stage in catalog['boss_groups'][str(request['group_id'])]:
                user.get('battle_progress', {}).pop(f'10:{stage}', None)
        else:
            star = request['star']
            drop = next((drop for need, drop in area['reward'] if need == star), None)
            total = sum(len(progress(user,10,s).get('stars', [])) for group in groups
                        for s in catalog['boss_groups'][str(group)])
            claimed = user.setdefault('boss_star_rewards', [])
            if not drop or total < star or star in claimed:
                raise ValueError('梦境星数不足或已经领奖')
            rewards = roll_drops(drop_config(drop), 1)
            claimed.append(star)
    elif command in (45104, 45108, 45110):
        group = request.get('id', request.get('group_id'))
        if command == 45110:
            valid = group in catalog['boss_groups'] or str(group) in catalog['boss_groups']
        else:
            valid = any(c['id'] == group for c in catalog['advance_pool'])
        if not valid:
            raise ValueError('梦境分组不存在')
        if command == 45104:
            config = next(c for c in catalog['advance'] if c['type'] == 2)
            pool = next(c for c in catalog['advance_pool'] if c['id'] == group)
            if not 1 <= request['diffculty_index'] <= len(config['monster_value']):
                raise ValueError('梦境难度无效')
            for field, choices in (('affix_index_list', pool['affix_pool']), ('time_index_list', pool['time_pool'])):
                if len(set(request[field])) != len(request[field]) or any(not 1 <= i <= len(choices) for i in request[field]):
                    raise ValueError('梦境词缀选项无效')
            user.setdefault('boss_affixes', {})[str(group)] = {k: deepcopy(request[k]) for k in
                ('affix_index_list', 'time_index_list', 'diffculty_index')}
        else:
            heroes = request['heroes_cfg']
            if len(heroes) > 3 or any(h and h not in {x['id'] for x in user['heroes']} for h in heroes):
                raise ValueError('梦境编队角色无效')
            user.setdefault('boss_teams', {})[str(group)] = list(heroes)
    else:
        layers = [c for c in catalog['abyss'] if c['activity_id'] == catalog['abyss'][0]['activity_id']]
        if command in (55002, 55004):
            stages = [s[1] for c in layers for s in c['stage_list'] if command == 55004 or c['level'] == request['layer']]
            if command == 55004:
                stages = [s for s in stages if s == request['stage_id']]
            if not stages:
                raise ValueError('深阱层级或关卡不存在')
            for stage in stages:
                user.get('battle_progress', {}).pop(f'1003:{stage}', None)
        else:
            ids = request['layer_list']
            claimed = user.setdefault('abyss_rewards', [])
            if not ids or len(set(ids)) != len(ids):
                raise ValueError('深阱领奖列表无效')
            configs = []
            for layer in ids:
                cfg = next((c for c in layers if c['level'] == layer), None)
                if not cfg or layer in claimed or any(not progress(user,1003,s[1]).get('clear_times') for s in cfg['stage_list']):
                    raise ValueError('深阱未通关或已领取')
                configs.append(cfg)
            rewards = [{'id': i, 'num': n} for cfg in configs for i, n in cfg['reward_list']]
            claimed.extend(ids)
    if rewards:
        grant_rewards(user, rewards)
    return response
