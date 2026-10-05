"""build 321 的全部可玩修正者及永久皮肤定义。"""

from runtime_data import load_runtime_table

# id: (skills, skins, astrolabes, module_level, exclusive_servant)
HERO_DEFINITIONS = load_runtime_table("HERO_DEFINITIONS", tuples=True)

# id: (recommended sigils, recommended warp skills, enchantment skills)
HERO_LOADOUTS = load_runtime_table("HERO_LOADOUTS", tuples=True)

def build_max_heroes(existing: list[dict] | None = None) -> list[dict]:
    """按客户端养成上限补齐角色，保留已经选择的有效皮肤。"""
    owned = {int(hero["id"]): hero for hero in (existing or [])}
    result = []
    for hid, (skills, skins, astrolabes, module, servant) in HERO_DEFINITIONS.items():
        selected = owned.get(hid, {}).get("skin_id", hid)
        result.append({
            "id": hid, "level": 100, "star": 600, "break_level": 8,
            "skin_id": selected if selected in skins else hid,
            "skills": list(skills), "skill_level": 35, "skill_attr_level": 15,
            "skins": list(skins), "astrolabes": list(astrolabes),
            "using_astrolabes": owned.get(hid, {}).get("using_astrolabes", list(astrolabes[:3])),
            "module_level": module, "weapon_exp": 99800, "weapon_break": 4,
            "servant_id": servant, "servant_stage": 5,
            "servant_uid": owned.get(hid, {}).get('servant_uid', hid),
            "trust_level": 5, "clear_times": 100,
            "equip_prefabs": list(HERO_LOADOUTS[hid][0]),
            "equip_ids": owned.get(hid, {}).get('equip_ids', [hid * 10 + pos for pos in range(1, 7)]),
            "battle_skin_id": owned.get(hid, {}).get('battle_skin_id', selected if selected in skins else hid),
        })
    return result
