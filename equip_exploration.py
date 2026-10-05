"""神域解析地图、路线选择和探索进度。"""

from copy import deepcopy
from functools import lru_cache
import time

from gameplay_protocol import read_client_data


@lru_cache(maxsize=1)
def exploration_catalog() -> dict:
    """读取地图节点、积分、任务和难度，关卡使用安装包的有效配置。"""
    return read_client_data('''(function()
        local r={nodes={},tasks={},points={}}
        local c=require('EquipBreakThroughMaterialMapCfg')
        for _,id in ipairs(c.get_id_list_by_map_id[1]) do r.nodes[#r.nodes+1]=c[id] end
        c=require('EquipBreakThroughMaterialTaskCfg')
        for _,id in ipairs(c.all) do r.tasks[#r.tasks+1]=c[id] end
        c=require('EquipBreakThroughMaterialPointCfg')
        for _,id in ipairs(c.all) do r.points[tostring(id)]=c[id].stage_point end
        r.difficulties=require('EquipBreakThroughMaterialDifficultyCfg').all
        r.rewards={}
        for _,id in ipairs(r.difficulties) do
            r.rewards[tostring(id)]=require('EquipBreakThroughMaterialDifficultyCfg')[id].reward_list
        end
        return r
    end)()''')


def exploration_pushes(user: dict) -> list[tuple]:
    """恢复地图和难度；未开始时仅初始化入口。"""
    catalog = exploration_catalog()
    state = user.get('equip_exploration', {})
    unlocked = state.get('unlocked_difficulties', catalog['difficulties'][:1]) if user.get('account_template') == 'normal' else catalog['difficulties']
    result = [(35001, {'unlock_difficulty': unlocked, 'difficulty': state.get('difficulty', 0),
                       'refresh_timestamp': state.get('refresh_timestamp', int(time.time()) + 7*86400),
                       'receive_list': state.get('claimed', [])})]
    if state.get('difficulty'):
        result.append((35003, deepcopy(state['map'])))
    return result


def available_node(user: dict, node_id: int) -> dict:
    """验证节点位于当前路线下一步，防止越过关卡领取奖励。"""
    state = user.get('equip_exploration', {}).get('map')
    if state is None:
        raise ValueError('神域解析尚未开始')
    nodes = exploration_catalog()['nodes']
    finished = state['progress_id_list']
    previous = next((n for n in nodes if finished and n['id'] == finished[-1]), None)
    allowed = previous['next_id_list'] if previous else [nodes[0]['id']]
    node = next((n for n in nodes if n['id'] == node_id), None)
    if node is None or node_id not in allowed or node_id in finished:
        raise ValueError('神域解析节点不在可行路线中')
    return node


def complete_node(user: dict, node_id: int) -> None:
    """推进一格探索路径，并按节点类型和列数累计积分与任务。"""
    node = available_node(user, node_id)
    state = user['equip_exploration']['map']
    state['progress_id_list'].append(node_id)
    points = exploration_catalog()['points'][str(node['stage_type'])]
    if points:
        state['total_points'] += points[node['col']-1]
    for task in state['assignment_list']:
        cfg = next(c for c in exploration_catalog()['tasks'] if c['id'] == task['id'])
        if cfg['condition'] == 1:
            task['now_progress'] = min(task['total_progress'], node['col'])
        elif cfg['condition'] == 2:
            task['now_progress'] = min(task['total_progress'], state['total_points'])


def update_health(user: dict, characters: list) -> None:
    """保存真实战斗生命比例，使后续关卡和治疗沿用当前生命。"""
    heroes = user['equip_exploration']['map']['hero_status']
    by_id = {h['hero_id']: h for h in heroes}
    for character in characters:
        maximum = character.get('3', 0)
        if maximum <= 0:
            continue
        hero_id = character['1']
        hero = by_id.get(hero_id)
        if hero is None:
            hero = {'hero_id': hero_id}
            heroes.append(hero)
        hero['health_rate'] = min(10000, max(0, character.get('2', 0) * 10000 // maximum))


def claim_rewards(user: dict, ids: list[int]) -> list[dict]:
    """仅领取已完成且未领取的任务，先整批校验再更新余额。"""
    from battle_rewards import grant_rewards
    state = user.get('equip_exploration', {})
    tasks = {t['id']: t for t in state.get('map', {}).get('assignment_list', [])}
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('领奖任务列表无效')
    for task_id in ids:
        task = tasks.get(task_id)
        if task is None or task_id in state.get('claimed', []) or task['now_progress'] < task['total_progress']:
            raise ValueError('任务未完成或已经领取')
    totals = {}
    for task_id in ids:
        for item, num in exploration_catalog()['rewards'][str(state['difficulty'])][task_id-1]:
            totals[item] = totals.get(item, 0) + num
    rewards = [{'id': item, 'num': num} for item, num in totals.items()]
    grant_rewards(user, rewards)
    state['claimed'].extend(ids)
    return rewards


def exploration_request(user: dict, command: int, request: dict) -> list[tuple]:
    """处理难度选择、增益、治疗、重置和连携设置。"""
    catalog = exploration_catalog()
    if command == 35100:
        difficulty = request['difficulty']
        if difficulty not in catalog['difficulties']:
            raise ValueError('神域解析难度不存在')
        stages = {1: 2040001, 2: 2041001, 3: 2042001}
        previous = user.get('equip_exploration', {})
        user['equip_exploration'] = {'difficulty': difficulty, 'claimed': previous.get('claimed', []),
            'refresh_timestamp': previous.get('refresh_timestamp', int(time.time()) + 7*86400),
            'map': {'map_id': 1, 'total_points': 0, 'progress_id_list': [], 'buff_list': [],
                    'choice_stage_list': [{'id': n['id'], 'stage': stages[n['stage_type']]}
                                          for n in catalog['nodes'] if n['stage_type'] in stages],
                    'choice_buff_list': [{'id': n['id'], 'buff_id': [101, 102, 103]}
                                         for n in catalog['nodes'] if n['stage_type'] == 4],
                    'assignment_list': [{'id': t['id'], 'now_progress': 0, 'total_progress': t['need']}
                                        for t in catalog['tasks']], 'hero_status': [], 'cooperate_unique_skill': 0}}
    elif command == 35102:
        previous = user.get('equip_exploration', {})
        user['equip_exploration'] = {'difficulty': 0, 'claimed': previous.get('claimed', []),
                                    'refresh_timestamp': previous.get('refresh_timestamp', int(time.time()) + 7*86400)}
    elif command in (35104, 35106):
        node = available_node(user, request['id'])
        state = user['equip_exploration']['map']
        if command == 35104:
            choices = next((c['buff_id'] for c in state['choice_buff_list'] if c['id'] == node['id']), [])
            if node['stage_type'] != 4 or request['buff_id'] not in choices:
                raise ValueError('神域解析增益选项无效')
            state['buff_list'].append(request['buff_id'])
        elif node['stage_type'] != 5:
            raise ValueError('当前节点不是治疗点')
        for hero in state['hero_status']:
            hero['health_rate'] = min(10000, hero['health_rate'] + (1000 if command == 35104 else 3000))
        complete_node(user, node['id'])
    elif command == 35110:
        user['equip_exploration']['map']['cooperate_unique_skill'] = request['id']
    else:
        raise ValueError('神域解析请求未实现')
    return exploration_pushes(user)
