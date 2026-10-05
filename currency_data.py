"""客户端资源 build 321 的完整货币定义：ItemCfg type=1 与 CurrencyIdMapCfg。"""

from runtime_data import load_runtime_table

# item_id: (ItemCfg.type, CurrencyIdMapCfg alias)，0 表示当前 ItemCfg 已不存在。
CURRENCY_DEFINITIONS = load_runtime_table("CURRENCY_DEFINITIONS", tuples=True)

NATIVE_CURRENCY_IDS = tuple(i for i, (kind, _) in CURRENCY_DEFINITIONS.items() if kind == 1)
MATERIAL_TOKEN_IDS = tuple(i for i, (kind, _) in CURRENCY_DEFINITIONS.items() if kind == 6)
GUILD_TOKEN_IDS = tuple(i for i, (kind, _) in CURRENCY_DEFINITIONS.items() if kind == 17)
RETIRED_CURRENCY_IDS = tuple(i for i, (kind, _) in CURRENCY_DEFINITIONS.items() if kind == 0)

DEFAULT_CURRENCY_AMOUNT = 99999
DRAW_CURRENCY_ID = 36  # ItemCfg[36] 共鸣辉芒；9 是委任情报点。
CORE_CURRENCY_FIELDS = {1: 'diamond', 2: 'gold', 4: 'stamina', 36: 'draw_tickets',
                        31: 'flower', 30: 'flower_ios', 32: 'flower_free'}


def build_currency_balances(user: dict | None = None) -> dict[int, int]:
    """补齐有效余额；已保存的核心字段优先，其他货币按 ID 覆盖默认值。"""
    user = user or {}
    initial = user.get('account_template') == 'normal'
    balances = {i: 0 if initial else DEFAULT_CURRENCY_AMOUNT for i in NATIVE_CURRENCY_IDS + MATERIAL_TOKEN_IDS}
    balances.update({
        1: user.get("diamond", 0 if initial else 99999),
        2: user.get("gold", 0 if initial else 9999999),
        4: user.get("stamina", 100 if initial else 240),
        36: user.get("draw_tickets", 0 if initial else 99),
    })
    for item_id, amount in user.get("currencies", {}).items():
        item_id = int(item_id)
        if item_id in balances:
            balances[item_id] = int(amount)
    for item_id, field in CORE_CURRENCY_FIELDS.items():
        if field in user:
            balances[item_id] = int(user[field])
    return balances


def materialize_currencies(user: dict) -> None:
    """把隐式默认余额写入存档，并明确保存三种移转之花及其平台归属。"""
    balances = build_currency_balances(user)
    user['currencies'] = {str(item): amount for item, amount in balances.items()}
    for item, field in CORE_CURRENCY_FIELDS.items():
        user[field] = balances[item]
