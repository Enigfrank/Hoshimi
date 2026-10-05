"""多维变量的本地路线、奖励与保存点；路线独立于官服随机排期。"""

from copy import deepcopy
from functools import lru_cache
import random

from battle_rewards import grant_rewards, spend_items
from client_attributes import polyhedron_attributes
from currency_data import build_currency_balances
from gameplay_protocol import decode_message, encode_message, read_client_data

POLYHEDRON_COMMANDS = set(range(18010, 18035, 2)) | {66000, 66002, 66004, 66034, 66036, 66038}


@lru_cache(maxsize=1)
def polyhedron_catalog() -> dict:
    """读取本机可用路线层、关卡、奖励物品和天赋配置。"""
    return read_client_data('''(function()
        local r={}
        for _,entry in ipairs({{'tiers','PolyhedronTierCfg'},{'stages','BattlePolyhedronStageCfg'},
            {'events','PolyhedronEventCfg'},{'artifacts','PolyhedronArtifactCfg'},
            {'effects','PolyhedronEffectCfg'},{'beacons','PolyhedronBeaconCfg'},
            {'terminal','PolyhedronTerminalCfg'},{'terminal_levels','PolyhedronTerminalLevelCfg'},
            {'settings','PolyhedronSettingCfg'},{'heroes','PolyhedronHeroCfg'},
            {'difficulties','PolyhedronDifficultyCfg'},{'policy','PolyhedronPolicyCfg'}}) do
            local c=require(entry[2]);local rows={}
            for _,id in ipairs(c.all) do rows[#rows+1]=c[id] end;r[entry[1]]=rows
        end
        return r
    end)()''')


def config_row(kind: str, item: int) -> dict:
    """按真实配置 ID 查询多维条目，未知 ID 直接拒绝。"""
    row = next((r for r in polyhedron_catalog()[kind] if r['id'] == item), None)
    if row is None:
        raise ValueError('多维配置不存在')
    return row


def normalize_data(data: dict) -> dict:
    """按客户端 SC 描述补齐必填值和空列表，使存档与推送具有相同结构。"""
    return decode_message(18001, encode_message(18001, data), 'sc')


def polyhedron_data(user: dict) -> dict:
    """恢复完整多维状态；新账号从可用主题的未开始状态初始化。"""
    if user.get('polyhedron'):
        return deepcopy(user['polyhedron'])
    from challenge_data import challenge_catalog
    shelf = next(r for r in challenge_catalog()['polyhedron'] if r['activity_id'] == 4407302)
    return normalize_data({'activity_id': shelf['activity_id'], 'game': {
        'state': 1, 'start_info': {'leader': {'hero_id': shelf['leader_hero_id'][0]}, 'difficulty': 1},
        'progress': {'tier_id': 1001, 'event': {}, 'stage': {'reward': {}}, 'cooperate_unique_skill_id': 0}},
        'decision': {}, 'terminal': {}, 'manual': {}, 'is_new': 0,
        'unlocked_hero_list': [{'hero_id': i} for i in set(shelf['leader_hero_id']+shelf['polyhedron_hero_id'])]})


def coin_change(progress: dict, amount: int) -> None:
    """局内金币保存于路线库存，不改变局外货币余额。"""
    rows = progress['stackable_item_list']
    row = next((r for r in rows if r['id'] == 1), None)
    if row is None:
        row = {'id': 1, 'num': 0};rows.append(row)
    if row['num']+amount < 0:
        raise ValueError('多维局内金币不足')
    row['num'] += amount


def update_max_health(data: dict) -> None:
    """按客户端原始公式重算最大生命，保留当前受伤量。"""
    progress = data['game']['progress']
    leader = data['game']['start_info']['leader']
    for hero in progress['hero_list']:
        template = config_row('heroes', hero['hero_id'])['standard_id']
        astrolabes = leader['astrolabe_list'] if hero['hero_id'] == leader['hero_id'] else next(
            h['astrolabe_id_list'] for h in data['unlocked_hero_list'] if h['hero_id'] == hero['hero_id'])
        maximum = polyhedron_attributes(template, astrolabes or [], progress['effect_list'],
            hero['difference_attribute_list'], len(progress['artifact_list']))[2]
        hero['health'] = max(0, maximum-max(0, hero['max_health']-hero['health']))
        hero['max_health'] = maximum


def add_hero(data: dict, hero_id: int) -> None:
    """按多维专用模板招募角色，并加入有空位的出战队伍。"""
    progress = data['game']['progress']
    template = config_row('heroes', hero_id)['standard_id']
    if any(h['hero_id'] == hero_id for h in progress['hero_list']):
        raise ValueError('多维角色已经招募')
    progress['hero_list'].append({'hero_id': hero_id, 'template_id': template, 'health': 0,
        'max_health': 0, 'reborn_cold_down': 0, 'difference_attribute_list': [], 'injured': 0, 'heal': 0, 'damage': 0})
    update_max_health(data)
    if len(progress['fight_hero_id_list']) < 3:
        progress['fight_hero_id_list'].append(hero_id)


def apply_item(data: dict, item: dict) -> None:
    """将奖励、商店物品或效果写入局内状态，再重算角色生命值。"""
    progress = data['game']['progress']
    kind, params = item['class'], item['params']
    if kind == 1:
        coin_change(progress, params[-1])
    elif kind == 3:
        add_hero(data, params[0])
    elif kind == 6:
        cfg = config_row('artifacts', params[0])
        existing = next((a for a in progress['artifact_list'] if a['id'] == cfg['id']), None)
        if existing:
            existing['level'] = min(existing['level']+1, cfg['max_level'])
        else:
            progress['artifact_list'].append({'id': cfg['id'], 'level': 1, 'life_time': 0})
        manual = data['manual']['sample_list']
        row = next((r for r in manual if r['id'] == cfg['id']), None)
        if row:
            row['state'] = 1
        else:
            manual.append({'id': cfg['id'], 'state': 1})
    elif kind in (4, 7):
        effect = config_row('effects', params[0])
        if effect['action'] == 3:
            for hero in progress['hero_list']:
                hero['health'] = min(hero['max_health'], hero['health']+hero['max_health']*effect['params'][0]//1000)
        elif effect['action'] == 6:
            for _, amount in effect['params']:
                coin_change(progress, amount)
        elif effect['moment'] == 1 and effect['action'] == 2:
            for hero in progress['hero_list']:
                values = {r['id']: r['value'] for r in hero['difference_attribute_list']}
                for attr, amount in effect['params']:
                    values[attr] = values.get(attr, 0)+amount
                hero['difference_attribute_list'] = [{'id': i, 'value': n} for i, n in values.items()]
        elif not any(e['id'] == effect['id'] for e in progress['effect_list']):
            progress['effect_list'].append({'id': effect['id'], 'life_time': 0})
    else:
        raise ValueError('多维物品类型无效')
    update_max_health(data)


def route_event(index: int, reward: int) -> dict:
    """本地路线选用客户端已有战斗地图；奖励类型由所选门确定。"""
    stages = polyhedron_catalog()['stages']
    event = next(e for e in polyhedron_catalog()['events'] if e['event_type'] == reward)
    return {'id': event['id'], 'stage_id': stages[index % len(stages)]['id'], 'reward_type': reward}


def open_stage(data: dict, event: dict) -> None:
    """进入实际战斗保存点，清除上一个节点的待选奖励与门。"""
    progress = data['game']['progress']
    progress['event'] = deepcopy(event)
    progress['stage'] = {'stage_id': event['stage_id'], 'save_point': 1, 'reward': {'round': 0, 'item_list': []},
        'params': [], 'gate_list': [], 'attribute_modify_list': []}


def open_gates(data: dict) -> None:
    """按真实层配置推进到选门保存点，路线末尾进入已结算状态。"""
    progress = data['game']['progress']
    tiers = polyhedron_catalog()['tiers']
    index = next(i for i, t in enumerate(tiers) if t['id'] == progress['tier_id'])
    if index == len(tiers)-1:
        data['game']['state'] = 3
        return
    choices = [1, 3, 4]
    if len(progress['hero_list']) < len(data['unlocked_hero_list']):
        choices[1] = 2
    progress['stage']['save_point'] = 3
    progress['stage']['gate_list'] = [{'index': i, 'event': route_event(index+i, kind)}
                                     for i, kind in enumerate(choices, 1)]


def make_rewards(data: dict) -> None:
    """使用所选门的奖励类别生成待选项，并保存随机结果防止重启重抽。"""
    progress = data['game']['progress']
    kind = progress['event']['reward_type']
    event = config_row('events', progress['event']['id'])
    if kind == 1:
        choices = [{'class': 1, 'params': [1, event['params'][0]]}]
    elif kind == 2:
        owned = {h['hero_id'] for h in progress['hero_list']}
        candidates = [h['hero_id'] for h in data['unlocked_hero_list'] if h['hero_id'] not in owned]
        choices = [{'class': 3, 'params': [h]} for h in random.sample(candidates, min(3, len(candidates)))]
    elif kind == 3:
        heroes = {h['hero_id'] for h in progress['hero_list']}
        owned = {a['id']: a['level'] for a in progress['artifact_list']}
        candidates = [a for a in polyhedron_catalog()['artifacts'] if
            (not a['exclusive_hero_id'] or a['exclusive_hero_id'] in heroes) and owned.get(a['id'], 0) < a['max_level']]
        choices = [{'class': 6, 'params': [a['id']]} for a in random.sample(candidates, min(3, len(candidates)))]
    else:
        choices = [{'class': 4, 'params': [i]} for i in (201, 202, 203)]
    progress['stage']['save_point'] = 2
    progress['stage']['reward'] = {'round': 1, 'item_list': choices}
    if not choices:
        open_gates(data)


def polyhedron_end(user: dict, data: dict, success: bool) -> None:
    """一局仅结算一次，保存实际节点分数、成长经验与难度通关记录。"""
    data['game']['state'] = 3
    if user.get('polyhedron_run_settled'):
        return
    user['polyhedron_run_settled'] = True
    completed = user.get('polyhedron_completed_nodes', 0)
    difficulty = data['game']['start_info']['difficulty']
    multiplier = config_row('difficulties', difficulty)['score']
    value = completed*75000*multiplier//1000
    exp = completed*100
    user['polyhedron_settlement'] = {'point': value, 'decision_exp': exp, 'terminal_exp': exp}
    if success and difficulty not in data['clear_difficulty_list']:
        data['clear_difficulty_list'].append(difficulty)
    if exp:
        grant_rewards(user, [{'id': 45, 'num': exp}, {'id': 46, 'num': exp}])


def settle_polyhedron(user: dict, battle: dict) -> None:
    """真实战斗结果更新局内剩余生命和保存点，重复结算由战斗会话拦截。"""
    data = polyhedron_data(user)
    progress = data['game']['progress']
    report = battle['reported']
    for character in report['info'].get('characters', []):
        # native 字段 2/3 是剩余/最大生命，转换后保存多维模板的绝对生命。
        hero = next((h for h in progress['hero_list'] if h['hero_id'] == character.get('1')), None)
        if hero and character.get('3', 0) > 0:
            hero['health'] = max(0, min(character['3'], character.get('2', 0)))*hero['max_health']//character['3']
    if report['result'] == 1:
        user['polyhedron_completed_nodes'] = user.get('polyhedron_completed_nodes', 0)+1
        make_rewards(data)
    elif report['result'] == 2:
        polyhedron_end(user, data, False)
    user['polyhedron'] = normalize_data(data)


def polyhedron_request(user: dict, command: int, request: dict) -> dict:
    """执行开局、选奖励、选门、换队和成长选择，状态先推送再返回请求结果。"""
    data = polyhedron_data(user)
    game, progress = data['game'], data['game']['progress']
    if command == 18010:
        if game['state'] == 2:
            raise ValueError('已有进行中的多维路线')
        heroes = request['hero_id_list']
        available = {h['hero_id'] for h in data['unlocked_hero_list']}
        if not heroes or len(heroes) > 3 or len(set(heroes)) != len(heroes) or not set(heroes) <= available:
            raise ValueError('多维队伍无效')
        difficulty = config_row('difficulties', request['difficulty'])
        if difficulty['unlock_difficulty'] and difficulty['unlock_difficulty'] not in data['clear_difficulty_list']:
            raise ValueError('多维难度前置尚未通关')
        if len(set(request['beacon_id_list'])) != len(request['beacon_id_list']):
            raise ValueError('多维信标重复')
        if not set(request['beacon_id_list']) <= set(data['beacon_id_list']):
            raise ValueError('多维信标未解锁')
        from battle_heroes import trial_battle_hero
        template = config_row('heroes', heroes[0])['standard_id']
        base = trial_battle_hero(template)['hero_base_info']
        astrolabes = next(h['astrolabe_id_list'] for h in data['unlocked_hero_list'] if h['hero_id'] == heroes[0])
        leader = {'hero_id': heroes[0], 'star': base['star'], 'skin': base['using_skin'],
            'break_level': base['break_level'], 'astrolabe_list': astrolabes,
            'weapon': {'breakthrough': base['weapon']['breakthrough'], 'servant': base['servant']},
            'weapon_module': {'level': base['weapon_module_level']}}
        game['start_info'] = {'leader': leader, 'difficulty': request['difficulty'],
            'beacon_id_list': request['beacon_id_list'], 'terminal_id_list': data['terminal']['upgrade_id_list']}
        game['state'] = 2
        progress.update({'tier_id': polyhedron_catalog()['tiers'][0]['id'], 'hero_list': [],
            'fight_hero_id_list': [], 'effect_list': [], 'artifact_list': [], 'attribute_list': [],
            'stackable_item_list': [], 'cooperate_unique_skill_id': 0})
        for hero in heroes:
            add_hero(data, hero)
        for beacon in request['beacon_id_list']:
            for effect in config_row('beacons', beacon)['effect_id_list']:
                apply_item(data, {'class': 4, 'params': [effect]})
        for talent in data['terminal']['upgrade_id_list']:
            apply_item(data, {'class': 4, 'params': [config_row('terminal', talent)['effect_id']]})
        open_stage(data, route_event(0, 1))
        user['polyhedron_completed_nodes'] = 0
        user['polyhedron_run_settled'] = False
    elif command in (18016, 18018):
        if command == 18018 and game['state'] == 2:
            polyhedron_end(user, data, False)
        else:
            game['state'] = 1
    elif command == 18034:
        data['is_new'] = 0
    elif command == 66002:
        data['terminal']['upgrade_id_list'] = []
        data['terminal']['reset_times'] += 1
    elif command == 66004:
        row = next((h for h in data['unlocked_hero_list'] if h['hero_id'] == request['hero_id']), None)
        if row is None:
            raise ValueError('多维角色未解锁')
        owned = next((h for h in user['heroes'] if h['id'] == request['hero_id']), None)
        ids = request['astrolabe_id_list']
        if not owned or len(ids) > 3 or len(set(ids)) != len(ids) or not set(ids) <= set(owned['astrolabes']):
            raise ValueError('多维神格配置无效')
        row['astrolabe_id_list'] = list(ids)
    elif command == 18032:
        ids = request['upgrade_id_list']
        if len(set(ids)) != len(ids):
            raise ValueError('多维天赋重复')
        rows = [config_row('terminal', i) for i in ids]
        levels = polyhedron_catalog()['terminal_levels']
        level = max((c for c in levels if c['exp'] <= build_currency_balances(user)[46]), key=lambda c: c['id'])
        if sum(c['cost'] for c in rows) > level['point'] or any(c['need_level'] > level['id'] for c in rows):
            raise ValueError('多维天赋点或等级不足')
        if any(0 not in c['pre_id_list'] and not set(c['pre_id_list']) & set(ids) for c in rows):
            raise ValueError('多维天赋前置条件不足')
        data['terminal']['upgrade_id_list'] = list(ids)
    elif command in (66034, 66036):
        if command == 66034:
            item = request['beacon_id'];config_row('beacons', item)
            if item in data['beacon_id_list']:
                raise ValueError('信标已解锁')
            data['beacon_id_list'].append(item)
        else:
            item = request['hero_id'];config_row('heroes', item)
            if any(h['hero_id'] == item for h in data['unlocked_hero_list']):
                raise ValueError('角色已解锁')
            spend_items(user, [{'id': 44, 'num': 1}])
            data['unlocked_hero_list'].append({'hero_id': item, 'astrolabe_id_list': []})
    elif command == 66000:
        rows = [c for c in polyhedron_catalog()['policy'] if c['activity_id'] == data['activity_id']]
        claimed = data['decision']['apply_id_list']
        allowed = [i for i, c in enumerate(rows, 1) if c['exp'] <= build_currency_balances(user)[45] and i not in claimed]
        indices = allowed if request['type'] == 1 else [request['level']]
        if not indices or any(i not in allowed for i in indices):
            raise ValueError('多维任务等级不足或已领奖')
        rewards = [{'id': i, 'num': n} for index in indices for i, n in rows[index-1]['rewards']]
        grant_rewards(user, rewards);claimed.extend(indices)
        user['polyhedron'] = normalize_data(data)
        return {'result': 0, 'reward_list': rewards}
    else:
        if game['state'] != 2:
            raise ValueError('多维路线尚未开始')
        stage = progress['stage']
        if command == 18012:
            choices = stage['reward']['item_list']
            index = request['index']
            if stage['save_point'] != 2 or not 0 <= index <= len(choices):
                raise ValueError('多维奖励选项无效')
            if index:
                apply_item(data, choices[index-1])
            stage['reward']['item_list'] = []
            open_gates(data)
            if game['state'] == 3:
                polyhedron_end(user, data, True)
        elif command == 18014:
            if stage['save_point'] != 3:
                raise ValueError('多维当前不处于选门保存点')
            selected = next((g['event'] for g in stage['gate_list'] if g['index'] == request['index']), None)
            if not selected:
                raise ValueError('多维门不存在')
            tiers = polyhedron_catalog()['tiers']
            index = next(i for i, t in enumerate(tiers) if t['id'] == progress['tier_id'])
            progress['tier_id'] = tiers[index+1]['id']
            open_stage(data, selected)
        elif command == 18028:
            heroes = request['fight_id_list']
            leader = game['start_info']['leader']['hero_id']
            owned = {h['hero_id'] for h in progress['hero_list'] if h['health']}
            if not heroes or len(heroes) > 3 or heroes[0] != leader or len(set(heroes)) != len(heroes) or not set(heroes) <= owned:
                raise ValueError('多维出战队伍无效')
            progress['fight_hero_id_list'] = list(heroes)
        elif command == 66038:
            progress['cooperate_unique_skill_id'] = request['cooperate_unique_skill_id']
        else:
            raise ValueError('当前多维节点没有对应操作')
    user['polyhedron'] = normalize_data(data)
    return {'result': 0}
