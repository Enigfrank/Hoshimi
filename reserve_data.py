"""编队按玩法和容器持久化，登录时恢复客户端队伍。"""

from copy import deepcopy

from gameplay_protocol import read_client_data


FIELDS = {63000: 'teams_info_list', 63006: 'chess_teams_info_list',
          63008: 'solo_challenge_teams_info_list', 63010: 'formation_teams_info_list'}


def reserve_data(user: dict) -> dict:
    """从账号恢复各类队伍，空存档保持客户端默认队伍。"""
    return deepcopy(user.get('reserve', {}))


def save_reserve(user: dict, command: int, request: dict) -> None:
    """合并单容器编队；重置仅移除指定玩法的指定容器。"""
    saved = user.setdefault('reserve', {})
    if command == 63002:
        for entries in saved.values():
            for entry in entries:
                if entry['team_type'] == request['team_type']:
                    entry['cont_teams'] = [c for c in entry['cont_teams'] if c['cont_id'] != request['cont_id']]
                    data = entry.get('data', [])
                    if isinstance(data, list):
                        entry['data'] = [d for d in data if d['cont_id'] != request['cont_id']]
                    else:
                        for rows in data.values():
                            rows[:] = [d for d in rows if d['cont_id'] != request['cont_id']]
        return
    container = request['cont_team']
    if len({t['team_index'] for t in container['teams']}) != len(container['teams']):
        raise ValueError('队伍索引重复')
    owned = {h['id'] for h in user.get('heroes', [])}
    for team in container['teams']:
        heroes = team['hero_list']
        active = [h for h in heroes if h['hero_id']]
        if len(heroes) > 3 or len({(h['hero_type'], h['hero_id']) for h in active}) != len(active):
            raise ValueError('队伍角色超限或重复')
        for hero in active:
            if hero['hero_type'] == 1 and hero['hero_id'] in owned:
                continue
            if hero['hero_type'] == 2 and read_client_data(f"require('HeroStandardSystemCfg')[{int(hero['hero_id'])}] ~= nil"):
                continue
            raise ValueError('队伍角色未拥有或试用无效')
    field = FIELDS[command]
    entries = saved.setdefault(field, [])
    entry = next((e for e in entries if e['team_type'] == request['team_type']), None)
    if entry is None:
        entry = {'team_type': request['team_type'], 'cont_teams': []}
        entries.append(entry)
    container = deepcopy(request['cont_team'])
    old = next((c for c in entry['cont_teams'] if c['cont_id'] == container['cont_id']), None)
    if old:
        by_index = {t['team_index']: t for t in old['teams']}
        by_index.update({t['team_index']: t for t in container['teams']})
        container['teams'] = list(by_index.values())
        entry['cont_teams'].remove(old)
    entry['cont_teams'].append(container)
    if 'data' in request:
        incoming = deepcopy(request['data'])
        if command == 63010:
            incoming = [incoming]
        if isinstance(incoming, list):
            rows = entry.setdefault('data', [])
            for item in incoming:
                identity = (item['cont_id'], item.get('team_index'))
                rows[:] = [d for d in rows if (d['cont_id'], d.get('team_index')) != identity]
                rows.append(item)
        else:
            data = entry.setdefault('data', {})
            for field, updates in incoming.items():
                rows = data.setdefault(field, [])
                for item in updates:
                    identity = (item['cont_id'], item.get('team_index'))
                    rows[:] = [d for d in rows if (d['cont_id'], d.get('team_index')) != identity]
                    rows.append(item)


def save_battle_team(user: dict, common: dict, config: dict) -> None:
    """普通编队随开战请求提交，按客户端关卡的容器配置保存。"""
    configured = config.get('team_type') or []
    if len(configured) < 2 or configured[0] < 0 or configured[1] < 0:
        return
    # 专属多队玩法通过各自的 630xx 请求带队伍索引，不能用默认索引覆盖。
    if common['type'] in (10, 100, 35, 1003, 67, 78, 15, 1006):
        return
    heroes = deepcopy(common['hero_list'])
    heroes.extend({'hero_id': 0, 'hero_type': 1, 'owner_id': 0} for _ in range(3-len(heroes)))
    team = {'team_index': 0, 'hero_list': heroes,
            'cooperate_unique_skill_id': common.get('cooperate_unique_skill_id', 0),
            'mimir_info': deepcopy((common.get('mimir_info') or [{}])[0])}
    save_reserve(user, 63000, {'team_type': configured[0],
        'cont_team': {'cont_id': configured[1], 'teams': [team]}})
    if config.get('need_default_team') == 1 and all(h['hero_type'] == 1 for h in heroes):
        save_reserve(user, 63000, {'team_type': 0, 'cont_team': {'cont_id': 0, 'teams': [team]}})
