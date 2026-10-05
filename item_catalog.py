"""客户端物品目录、发放校验与可导出的中文查阅表。"""

from functools import lru_cache

from gameplay_protocol import read_client_data

ITEM_TYPES = {1: '货币', 2: '修正者', 3: '修正者情报', 4: '剧情收集', 5: '礼包',
              6: '材料', 7: '刻印', 8: '皮肤', 9: '钥从', 10: '好感礼物', 11: '头像',
              12: '头像框', 13: '贴纸', 14: '兑换券', 15: '家具', 16: '食材', 17: '社团物品',
              18: '贴纸背景', 19: '宿舍货币', 20: '表情', 21: '大厅场景', 22: '个人标签',
              23: '名片背景', 24: '家具图纸', 25: '贴纸前景', 26: '聊天气泡',
              27: '活动物品', 28: '游戏图标'}


@lru_cache(maxsize=1)
def item_catalog() -> dict[int, dict]:
    """读取两张物品表，使用角色和皮肤配置补齐没有名称的物品。"""
    rows = read_client_data('''(function()
        local r={};local seen={}
        local heroes=require('HeroCfg');local skins=require('SkinCfg')
        for _,name in ipairs({'ItemCfg','ItemCfg2'}) do
            local c=require(name)
            for _,id in ipairs(c.all or {}) do
                local v=c[id]
                if v and not seen[id] then
                    seen[id]=true
                    local label=v.name
                    if not label or label=='' then label=(skins[id] and skins[id].name) or (heroes[id] and heroes[id].name) end
                    r[#r+1]={id=id,name=label or ('物品 '..id),type=v.type,
                        sub_type=v.sub_type or 0,description=v.desc or ''}
                end
            end
        end
        return r
    end)()''')
    return {row['id']: {**row, 'type_name': ITEM_TYPES.get(row['type'], '其他')} for row in rows}


def validate_rewards(rewards: list[dict]) -> list[dict]:
    """校验物品与正整数数量，合并重复 ID，限制一次发放的独立实例数量。"""
    totals = {}
    for reward in rewards:
        item, number = reward['id'], reward['num']
        if type(item) is not int or type(number) is not int or item not in item_catalog():
            raise ValueError('物品 ID 或数量无效')
        if not 0 < number <= 2_000_000_000:
            raise ValueError('数量须为 1 至 2000000000 的整数')
        totals[item] = totals.get(item, 0) + number
    if not totals or any(n > 2_000_000_000 for n in totals.values()):
        raise ValueError('物品列表为空或数量超过上限')
    if sum(n for i, n in totals.items() if item_catalog()[i]['type'] in (7, 9)) > 1000:
        raise ValueError('单次最多发放 1000 个刻印或钥从实例')
    return [{'id': i, 'num': n} for i, n in totals.items()]


def give_items(user: dict, rewards: list[dict]) -> list[dict]:
    """向账号库存发放有效物品，保存由调用方与其他账号变更一起完成。"""
    from battle_rewards import grant_rewards
    from currency_data import build_currency_balances
    values = validate_rewards(rewards)
    balances = build_currency_balances(user)
    for reward in values:
        if balances.get(reward['id'], user.get('materials', {}).get(str(reward['id']), 0)) + reward['num'] > 2_000_000_000:
            raise ValueError('发放后余额超过 2000000000')
    grant_rewards(user, values)
    return values
