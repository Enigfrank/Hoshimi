"""单人战斗队伍、会话和结算数据。"""

import time
from functools import lru_cache
from itertools import count

from gameplay_protocol import decode_message, read_client_data
from proto_bridge import get_bridge
from battle_rewards import drop_config, roll_drops, grant_rewards
from hero_preferences import hero_info_data
from battle_rewards import equipment_data
from battle_rewards import spend_items
from task_progress import update_task_progress
from battle_heroes import owned_battle_hero, trial_battle_hero
from loadout_storage import servant_data

_BATTLE_IDS = count(int(time.time()))


STAGE_CONFIGS = {
    1: 'BattleChapterStageCfg', 601: 'BattleActivityStoryStageCfg', 2: 'BattleDailyStageCfg',
    7: 'BattleTowerStageCfg', 8: 'BattleEnchantmentStageCfg', 9: 'BattleEquipStageCfg',
    10: 'BattleBossStageCfg', 100: 'BattleBossStageCfg', 11: 'BattleMythicStageCfg',
    12: 'BattleBaseTeachStageCfg', 13: 'BattleHeroTeachStageCfg',
    35: 'BattleMythicFinalCfg', 53: 'BattleEquipSeizureStageCfg',
    40: 'BattleEquipBreakThroughMaterialStageCfg', 1003: 'BattleAbyssCfg',
    1006: 'BattleAdvanceTestStageCfg', 52: 'BattlePolyhedronStageCfg',
    78: 'BattleRogueTeamStageCfg', 57: 'BattleHeartDemonStageCfg',
    1002: 'BattleDamageTestCfg', 67: 'BattleCoreVerificationCfg',
    15: 'BattleChessStageCfg',
    1009: 'BattleActivityAdvanceMonsterTestCfg',
}


@lru_cache(maxsize=512)
def stage_config(stage_type: int, stage_id: int) -> dict:
    """按实际玩法校验关卡配置，拒绝不存在的关卡。"""
    name = STAGE_CONFIGS.get(stage_type)
    if name is None:
        return {}
    if stage_type == 11:
        from challenge_data import challenge_catalog
        catalog = challenge_catalog()
        for difficulty in catalog['mythic']:
            partitions = [difficulty['main_partition']] + difficulty['sub_partition_list']
            if stage_id in partitions:
                actual = catalog['mythic_stages'][partitions.index(stage_id)]
                return read_client_data(f"require('{name}')[{actual}]")
        return {}
    if stage_type in (67, 1006):
        info = 'CoreVerificationInfoCfg' if stage_type == 67 else 'AdvanceTestCfg'
        return read_client_data(f"(function() local c=require('{info}')[{int(stage_id)}]; "
                                f"return c and require('{name}')[c.stage_id] or {{}} end)()")
    return read_client_data(f"require('{name}')[{int(stage_id)}] or {{}}")


def start_battle(user: dict, request: dict) -> tuple[dict, dict]:
    """校验关卡和所选角色，并下发与存档一致的战斗队伍。"""
    common = request['common_info']
    if common['type'] == 35:
        from challenge_data import challenge_catalog
        difficulty = user.get('mythic_final_difficulty', 1)
        final = next((c for c in challenge_catalog()['final'] if c['id'] == difficulty), None)
        index = common['dest']
        if final is None or not 1 <= index <= len(final['stage_list']):
            raise ValueError('终末黑区队伍序号无效')
        stages = final['stage_list'][index-1]
        cleared = user.get('mythic_final_runs', {}).get(str(difficulty), {}).get(str(index), {}).get('stages', [])
        stage_id = next((s for s in stages if s not in cleared), None)
        if stage_id is None:
            raise ValueError('该队伍路线已通关，请重置后重试')
        cfg = stage_config(35, stage_id)
    else:
        cfg = stage_config(common['type'], common['dest'])
    if not cfg:
        raise ValueError('关卡不存在或尚未实现对应玩法')
    times = common.get('battle_times', 1)
    if not 1 <= times <= 5:
        raise ValueError('战斗倍率无效')
    if user.get('stamina', 240) < cfg.get('cost', 0) * times:
        raise ValueError('吨吨值不足')
    if common['type'] == 40:
        from equip_exploration import available_node
        available_node(user, common.get('index', 0))
        choices = user['equip_exploration']['map']['choice_stage_list']
        if not any(n['id'] == common['index'] and n['stage'] == common['dest'] for n in choices):
            raise ValueError('神域解析关卡不属于当前节点')
    if common['type'] == 52:
        from polyhedron_game import polyhedron_data
        poly = polyhedron_data(user)
        route = poly['game']['progress']
        selected = [h['hero_id'] for h in common['hero_list'] if h['hero_id']]
        if poly['game']['state'] != 2 or route['stage']['save_point'] != 1 or route['stage']['stage_id'] != common['dest']:
            raise ValueError('多维关卡不属于当前保存点')
        if selected != route['fight_hero_id_list']:
            raise ValueError('多维战斗队伍与路线不一致')
    bridge = get_bridge()
    heroes = hero_info_data(user)['hero_info_list']
    equipment = equipment_data(user)['equip_list']
    by_id = {h['hero_base_info']['id']: h for h in heroes}
    servants = servant_data(user)['servant_list']
    team = []
    for selection in common['hero_list']:
        hero_id = selection['hero_id']
        if not hero_id:
            continue
        hero_type = selection['hero_type']
        if hero_type == 2:
            member = trial_battle_hero(hero_id)
            if not member:
                raise ValueError('试用角色不存在')
        elif hero_type == 1 and hero_id in by_id:
            member = owned_battle_hero(by_id[hero_id], equipment, servants)
        else:
            raise ValueError('角色未拥有')
        team.append(member)
    if not team:
        raise ValueError('战斗队伍为空')
    now = int(time.time())
    battle_id = max(next(_BATTLE_IDS), user.get('last_battle_id', 0)+1)
    user['last_battle_id'] = battle_id
    battle = {'id': battle_id, 'started': now, 'common': common, 'config': cfg,
              'reported': None, 'settlement': None}
    if common['type'] == 35:
        battle['final_difficulty'] = difficulty
    player = {'player_id': user['uid'], 'player_battle_info': {
        'channel': 1, 'server': 1, 'hero_list': team, 'nick': user.get('nick', 'Developer'),
        'level': user.get('level', 80), 'icon': user.get('icon', 1084), 'frame': user.get('icon_frame', 2001)},
        'player_room_info': {'is_master': 1, 'is_ready': 1}}
    return battle, {'player_info': player}


def start_story(request: dict) -> dict:
    """剧情观看使用独立完成协议，拒绝将战斗关卡当作剧情通关。"""
    kind = 601 if request.get('activity_id') else 1
    cfg = stage_config(kind, request['stage_id'])
    if not cfg or cfg.get('tag') != 2:
        raise ValueError('请求的关卡不是剧情节点')
    return {'id': next(_BATTLE_IDS), 'started': int(time.time()),
            'common': {'type': kind, 'dest': request['stage_id'], 'activity_id': request.get('activity_id', 0),
                       'hero_list': [], 'battle_times': 1}, 'config': cfg,
            'reported': {'result': 1, 'info': {}}, 'settlement': None}


def settle_battle(user: dict, battle: dict, battle_id: int) -> dict:
    """根据 native 实际结果结算一次；重复请求返回同一结果。"""
    if not battle or battle['id'] != battle_id:
        raise ValueError('战斗 ID 不匹配')
    if battle['settlement'] is not None:
        return battle['settlement']
    report = battle['reported']
    if report is None:
        raise ValueError('尚未收到战斗结果')
    result = min(report['result'], 3)
    info = report['info']
    common = battle['common']
    win = result == 1
    seconds = info['2'] // 1000 if '2' in info else max(0, int(time.time()) - battle['started'])
    stars = []
    for index, condition in enumerate(battle['config'].get('three_star_need') or [], 1):
        kind = condition[0]
        need = condition[1] if len(condition) > 1 else 1
        value = 0
        achieved = False
        if kind in (1, 3, 4, 9, 10, 14):
            field = {1: '3', 3: '4', 4: '2', 9: '5', 10: '6', 14: '9'}[kind]
            value = seconds if kind == 4 else info.get(field, 0)
            achieved = value <= need
        elif kind in (2, 13):
            value = int(info.get('3' if kind == 2 else '9', 0) == 0)
            achieved = value == 1
        elif kind == 8:
            value = int(win)
            achieved = win
        elif kind == 11:
            value = info.get('7', 0)
            achieved = value >= need
        elif kind == 12:
            value = int(any(h['hero_id'] == need for h in common['hero_list']))
            need = 1
            achieved = value == 1
        elif kind in (15, 16):
            items = dict(zip(info.get('12', []), info.get('13', [])))
            item_id = condition[2] if kind == 15 else need
            if kind == 16:
                need = 1
            value = items.get(item_id, 0)
            achieved = value >= need
        stars.append({'star_id': index, 'now_progress': value, 'need_progress': need,
                      'is_achieve': int(win and achieved)})
    key = f"{common['type']}:{common['dest']}"
    progress = user.setdefault('battle_progress', {}).setdefault(key, {'clear_times': 0, 'stars': []})
    times = max(1, min(common.get('battle_times', 1), 5))
    if win:
        cost = battle['config'].get('cost', 0) * times
        if cost:
            spend_items(user, [{'id': 4, 'num': cost}])
            update_task_progress(user, 350, cost, 4)
        update_task_progress(user, 402, times)
        if common['type'] == 11:
            update_task_progress(user, 453, times)
        elif common['type'] in (10, 100):
            update_task_progress(user, 405, times, 301)
        progress['clear_times'] += times
        progress['stars'] = sorted(set(progress['stars']) | {s['star_id'] for s in stars if s['is_achieve']})
        progress['best_time'] = min(progress.get('best_time', seconds), seconds)
        progress['last_heroes'] = [h['hero_id'] for h in common['hero_list'] if h['hero_id']]
        if common['type'] == 35:
            from challenge_data import challenge_catalog
            difficulty = battle['final_difficulty']
            runs = user.setdefault('mythic_final_runs', {}).setdefault(str(difficulty), {})
            team = runs.setdefault(str(common['dest']), {'stages': [], 'use_time': 0})
            team['stages'].append(battle['config']['id'])
            team['use_time'] += seconds
            final = next(c for c in challenge_catalog()['final'] if c['id'] == difficulty)
            if all(all(s in runs.get(str(i), {}).get('stages', []) for s in stages)
                   for i, stages in enumerate(final['stage_list'], 1)):
                cleared = user.setdefault('mythic_final_cleared', [])
                if difficulty not in cleared:
                    cleared.append(difficulty)
        if common['type'] == 40:
            from equip_exploration import complete_node, update_health
            update_health(user, info.get('characters', []))
            complete_node(user, common['index'])
    gains = roll_drops(drop_config(battle['config'].get('drop_lib_id', 0)), times) if win else []
    if gains:
        grant_rewards(user, gains)
    if common['type'] == 52:
        from polyhedron_game import settle_polyhedron
        settle_polyhedron(user, battle)
    battle['settlement'] = {'result': 0, 'battle_result': {
        'battle_id': battle_id, 'result': result, 'dest': common['dest'], 'timestamp': int(time.time()),
        'clear_times': progress['clear_times'], 'target_times': times, 'use_seconds': seconds,
        'star_list': stars, 'all_drop_list': [{'battle_times': times, 'gain_list': gains}],
        'hero_id_list': [h['hero_id'] for h in common['hero_list'] if h['hero_id']]}}
    return battle['settlement']
