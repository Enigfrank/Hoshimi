"""本地商店交易、库存和购买次数的持久化。"""

from functools import lru_cache
from datetime import datetime, timedelta, timezone
import time

from battle_rewards import grant_rewards, spend_items
from gameplay_protocol import decode_message, read_client_data
from proto_bridge import get_bridge
from push_data import SHOP_GOODS_NOREFRESH
from supply_data import build_supply_goods, SUPPLY_DEFINITIONS
from task_progress import update_task_progress
from server_clock import refresh_hour


@lru_cache(maxsize=1)
def shop_catalog() -> dict:
    """一次读取静态商品，避免登录按数千商品重复执行 Lua 查询。"""
    return read_client_data('''(function()
        local r={}
        for _,name in ipairs({'ShopCfg','ShopCfg2','ShopCfg3','ShopCfg4'}) do
            local c=require(name)
            for _,id in ipairs(c.all or {}) do
                if c[id] then r[tostring(id)]=c[id] end
            end
        end
        return r
    end)()''')


@lru_cache(maxsize=8192)
def shop_good(good_id: int, shop_id: int) -> dict:
    """只返回实际已下发到指定商店的商品配置。"""
    if good_id >= 900000000:
        description = good_id - 900000000
        entry = SUPPLY_DEFINITIONS.get(description)
        if entry and entry[1] == shop_id:
            return {'goods_id': good_id, 'description': description, 'shop_id': shop_id,
                    'cost_id': 1, 'cost': 1, 'limit_num': -1, 'give': 1}
        return {}
    if good_id not in SHOP_GOODS_NOREFRESH.get(shop_id, []):
        return {}
    return shop_catalog().get(str(good_id), {})


def shop_stock(user: dict) -> dict:
    """恢复所有商店已购买次数，保持原有商品下发范围。"""
    refresh_shop_periods(user)
    supplies = build_supply_goods()
    goods = {sid: list(ids) for sid, ids in SHOP_GOODS_NOREFRESH.items()}
    for sid, items in supplies.items():
        goods.setdefault(sid, []).extend(item['goods_id'] for item in items)
    result = decode_message(20009, get_bridge().encode_sc_20009(goods), 'sc')
    counts = user.get('shop_purchases', {})
    for shop in result['shop_item_list']:
        for item in shop['goods_list']:
            item['buy_times'] = counts.get(str(shop['shop_id']), {}).get(str(item['goods_id']), 0)
            item['next_refresh_timestamp'] = period_end(shop_good(item['goods_id'], shop['shop_id']).get('refresh_cycle', 0))
    return result


def buy_goods(user: dict, request: dict) -> dict:
    """校验服务器价格、限购和余额，整批扣款发货并保存购买计数。"""
    refresh_shop_periods(user)
    shop_id = request['shop_id']
    rows = request['buy_goods_list']
    if not rows or len({row['buy_id'] for row in rows}) != len(rows):
        raise ValueError('商品列表为空或重复')
    costs, rewards = [], []
    purchases = user.get('shop_purchases', {}).get(str(shop_id), {})
    for row in rows:
        cfg = shop_good(row['buy_id'], shop_id)
        count = row['buy_num']
        if not cfg or count <= 0:
            raise ValueError('商品无效或数量无效')
        for kind, need in cfg.get('level_limit') or []:
            from passport_progress import passport_level
            current = user.get('level', 80) if kind == 1 else passport_level(user)
            if current < need:
                raise ValueError('等级不足')
        bought = purchases.get(str(row['buy_id']), 0)
        if cfg.get('limit_num', -1) > 0 and bought + count > cfg['limit_num']:
            raise ValueError('超出商品限购次数')
        price = cfg.get('cost', 0)
        currency = cfg.get('cost_id', 0)
        if cfg.get('cheap_cost_id') and cfg.get('cheap_cost', 0) > 0 and not cfg.get('is_limit_time_discount'):
            price, currency = cfg['cheap_cost'], cfg['cheap_cost_id']
        if price:
            costs.append({'id': currency, 'num': price * count})
        if cfg.get('cost_2', 0):
            costs.append({'id': cfg['cost_id_2'], 'num': cfg['cost_2'] * count})
        if cfg.get('description'):
            item = read_client_data(f"require('RechargeShopDescriptionCfg')[{cfg['description']}]")
            if item['type'] == 5:
                rewards.extend({'id': item_id, 'num': amount * count * cfg.get('give', 1)}
                               for item_id, amount in item['param'])
            else:
                item_id = item['param'][0] if item['type'] == 6 else cfg['description']
                rewards.append({'id': item_id, 'num': count * cfg.get('give', 1)})
        else:
            item_id = cfg['give_id']
            item = read_client_data(f"require('ItemCfg')[{item_id}] or require('ItemCfg2')[{item_id}]")
            if item['type'] == 5 and item.get('sub_type') == 501:
                rewards.extend({'id': i, 'num': n * count * cfg.get('give', 1)} for i, n in item['param'])
            else:
                rewards.append({'id': item_id, 'num': count * cfg.get('give', 1)})
    spend_items(user, costs)
    grant_rewards(user, rewards)
    counts = user.setdefault('shop_purchases', {}).setdefault(str(shop_id), {})
    for row in rows:
        key = str(row['buy_id'])
        counts[key] = counts.get(key, 0) + row['buy_num']
    update_task_progress(user, 600, sum(row['buy_num'] for row in rows), shop_id)
    return {'result': 0, 'give_items': rewards, 'cost_items': costs}


def period_end(cycle: int, now: int | None = None) -> int:
    """按客户端日、周、月限购标记计算下一次北京时间刷新。"""
    hour = refresh_hour()
    current = datetime.fromtimestamp(int(time.time()) if now is None else now, timezone(timedelta(hours=8))) - timedelta(hours=hour)
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if cycle == 4:
        end = midnight + timedelta(days=1)
    elif cycle == 3:
        end = midnight + timedelta(days=7-current.weekday())
    elif cycle == 2:
        end = midnight.replace(year=current.year + int(current.month == 12), month=current.month % 12 + 1, day=1)
    else:
        return 0
    return int((end + timedelta(hours=hour)).timestamp())


def refresh_shop_periods(user: dict, now: int | None = None) -> None:
    """只重置到期的周期限购，永久限购与累计购买记录保持原值。"""
    deadlines = user.setdefault('shop_periods', {})
    for shop, goods in user.get('shop_purchases', {}).items():
        for good in list(goods):
            cycle = shop_good(int(good), int(shop)).get('refresh_cycle', 0)
            end = period_end(cycle, now)
            if not end:
                continue
            key = f'{shop}:{good}'
            if key in deadlines and deadlines[key] != end:
                goods[good] = 0
            deadlines[key] = end
