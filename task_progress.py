"""任务进度、周期活跃度与奖励领取的持久化。"""

import time

from battle_rewards import grant_rewards
from gameplay_protocol import read_client_data
from server_clock import business_day


def refresh_task_periods(user: dict, now: int | None = None) -> None:
    """以北京时间重置每日和每周任务，保留剧情与长期任务。"""
    from gameplay_data import client_catalog
    day = business_day(int(time.time()) if now is None else now)
    periods = {6: day, 5: (day-4) // 7}
    saved = user.setdefault('task_periods', {})
    tasks = user.setdefault('tasks', {})
    for kind, current in periods.items():
        key = str(kind)
        if key in saved and saved[key] != current:
            for cfg in client_catalog()['tasks']:
                if cfg['type'] == kind:
                    tasks.pop(str(cfg['id']), None)
            user.setdefault('task_points', {}).pop('1' if kind == 6 else '3', None)
            if kind == 5:
                user['passport_weekly_exp'] = 0
        saved[key] = current


def update_task_progress(user: dict, condition: int, amount: int = 1, parameter: int = 0) -> None:
    """由已验证的登录、通关、消耗和交互事件更新当前可见任务。"""
    from gameplay_data import client_catalog, task_data
    active = {row['id'] for row in task_data(user)['assignment_list']}
    for cfg in client_catalog()['tasks']:
        if cfg['id'] not in active or cfg['condition'] != condition:
            continue
        params = cfg.get('additional_parameter') or []
        if params and params[0] not in (0, parameter):
            continue
        entry = user.setdefault('tasks', {}).setdefault(str(cfg['id']), {'progress': 0, 'complete_flag': 0})
        if entry['complete_flag'] == 0:
            entry['progress'] = min(cfg['need'], entry['progress'] + amount)


def claim_tasks(user: dict, ids: list[int]) -> dict:
    """整批校验任务已完成且未领取，然后保存领取状态并发放真实奖励。"""
    from gameplay_data import client_catalog, task_data
    active = {row['id'] for row in task_data(user)['assignment_list']}
    catalog = {cfg['id']: cfg for cfg in client_catalog()['tasks']}
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('任务列表为空或重复')
    rewards = []
    for task_id in ids:
        cfg = catalog.get(task_id)
        progress = user.get('tasks', {}).get(str(task_id), {})
        if task_id not in active or not cfg or progress.get('complete_flag') or progress.get('progress', 0) < cfg['need']:
            raise ValueError('任务尚未完成或奖励已领取')
        rewards.extend({'id': item, 'num': amount} for item, amount in cfg['reward'])
    for task_id in ids:
        user['tasks'][str(task_id)]['complete_flag'] = 1
    grant_rewards(user, rewards)
    update_task_progress(user, 300, sum(r['num'] for r in rewards if r['id'] == 22), 22)
    return {'result': 0, 'reward_list': rewards}


def claim_task_points(user: dict, request: dict) -> dict:
    """领取日、周或新手活跃度节点，防止重复领取。"""
    point_id = request.get('activity_pt_id') or 1
    cfg = read_client_data(f"require('ActivityPtCfg')[{int(point_id)}] or {{}}")
    target = request['need_active_point']
    point = user.setdefault('task_points', {}).setdefault(str(point_id), {'point': 0, 'claimed': []})
    if not cfg or target not in cfg['target'] or point['point'] < target or target in point['claimed']:
        raise ValueError('活跃度未达到或奖励已领取')
    rewards = [{'id': item, 'num': amount} for item, amount in cfg['reward'][cfg['target'].index(target)]]
    grant_rewards(user, rewards)
    point['claimed'].append(target)
    return {'result': 0, 'reward_list': rewards}
