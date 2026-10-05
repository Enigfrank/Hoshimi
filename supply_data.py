"""全部客户端补给描述；动态商品采用本地编号及移转之辉价格。"""

from runtime_data import load_runtime_table

# description_id: (item_type, shop_id)
SUPPLY_DEFINITIONS = load_runtime_table("SUPPLY_DEFINITIONS", tuples=True)

def build_supply_goods() -> dict[int, list[dict]]:
    """将全部补给定义转换为动态商品配置；本地商品统一售价 1 移转之辉。"""
    shops = {sid: [] for sid in (3, 4, 5, 6, 15, 16, 17, 18, 24, 25, 34, 35, 36, 37, 42)}
    for description, (_, sid) in SUPPLY_DEFINITIONS.items():
        shops[sid].append({"goods_id": 900000000 + description,
                           "description": description, "cost_id": 1, "cost": 1})
    return shops
