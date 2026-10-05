"""仓库消耗品和可选礼包的扣除、奖励与持久化。"""

from collections import Counter
from functools import lru_cache

from battle_rewards import drop_config, roll_drops, grant_rewards, spend_items
from gameplay_protocol import read_client_data


@lru_cache(maxsize=256)
def usable_item(item: int) -> dict:
    """取得实际使用规则，不接受客户端提供奖励或到期时间。"""
    return read_client_data(f"require('ItemCfg')[{int(item)}] or require('ItemCfg2')[{int(item)}] or {{}}")


def use_items(user: dict, request: dict) -> dict:
    """整批校验后消耗库存，按本机配置发放体力、礼包和自选奖励。"""
    costs, rewards = [], []
    if not request['use_item_list']:
        raise ValueError('使用物品列表为空')
    for entry in request['use_item_list']:
        item, num = entry['item_info']['id'], entry['item_info']['num']
        cfg = usable_item(item)
        if not cfg or not cfg.get('use') or not 1 <= num <= 9999:
            raise ValueError('物品不可使用或数量无效')
        # 当前存档只创建永久实例；客户端不得伪造临时物品的到期字段。
        if entry['item_info'].get('time_valid', 0):
            raise ValueError('未持有该临时物品实例')
        subtype, params = cfg['sub_type'], cfg.get('param') or []
        selected = entry['use_list']
        if subtype in (401, 403, 501):
            if selected or not all(isinstance(r, list) and len(r) == 2 for r in params):
                raise ValueError('物品使用参数无效')
            rewards.extend({'id': i, 'num': n*num} for i, n in params)
        elif subtype in (504, 506, 515):
            if len(selected) != 1 or not 1 <= selected[0] <= len(params):
                raise ValueError('自选礼包选项无效')
            item_id, amount = params[selected[0]-1]
            rewards.append({'id': item_id, 'num': amount*num})
        elif subtype == 507:
            if selected or not params or not drop_config(params[0]):
                raise ValueError('随机礼包掉落配置无效')
            rewards.extend(roll_drops(drop_config(params[0]), num))
        elif subtype == 408:
            if selected or not params:
                raise ValueError('剧情道具参数无效')
            stories = user.setdefault('read_stories', [])
            if params[0] not in stories:
                stories.append(params[0])
        else:
            raise ValueError('该物品需要尚未实现的专用使用流程')
        costs.append({'id': item, 'num': num})
    totals = Counter()
    for reward in rewards:
        totals[reward['id']] += reward['num']
    if totals[4]+user.get('stamina', 240) > 999:
        raise ValueError('体力超过可持有上限')
    spend_items(user, costs)
    rewards = [{'id': i, 'num': n} for i, n in totals.items()]
    grant_rewards(user, rewards)
    return {'result': 0, 'drop_list': rewards}
