"""账号角色、皮肤与场景解锁，以及 Developer 的装饰和钥从迁移。"""

from copy import deepcopy
from functools import lru_cache

from gameplay_protocol import read_client_data, decode_message
from battle_rewards import equipment_data
from item_catalog import item_catalog
from hero_data import build_max_heroes
from loadout_storage import servant_data
from proto_bridge import get_bridge

DECORATION_FIELDS = {11: 'icon_list', 13: 'all_sticker_list', 18: 'all_background_list',
                     21: 'poster_background_list', 22: 'tag_info_list', 23: 'information_background_list',
                     25: 'all_foreground_list', 26: 'chat_bubble_list', 28: 'game_icon'}


@lru_cache(maxsize=1)
def unlock_catalog():
    """读取全部钥从、有效场景以及各可玩角色的完整皮肤。"""
    return read_client_data('''(function()
        local r={servants={},scenes={},skins={},views={}}
        for _,id in ipairs(require('WeaponServantCfg').all) do r.servants[#r.servants+1]=id end
        for _,id in ipairs(require('HomeSceneSettingCfg').all) do r.scenes[#r.scenes+1]=id end
        local views=require('HomeSceneViewCfg')
        for _,id in ipairs(views.all) do r.views[#r.views+1]=views[id] end
        local c=require('SkinCfg')
        for _,id in ipairs(c.all) do r.skins[#r.skins+1]={id=id,hero=c[id].hero} end
        return r
    end)()''')


def unlock_characters(user):
    """解锁全部满配角色、皮肤与场景，保存实际装备且重复执行复用实例。"""
    heroes = build_max_heroes()
    previous = {h['id']: h for h in user.get('heroes', [])}
    equipment = {e['equip_id']: e for e in equipment_data(user)['equip_list']}
    servants = servant_data(user)['servant_list']
    next_equip = max(user.get('next_equip_uid', 1), max(equipment, default=0) + 1)
    next_servant = max(user.get('next_servant_uid', 1), max((s['uid'] for s in servants), default=0) + 1)
    used_equips, used_servants = set(), set()
    skins = {}
    for cfg in unlock_catalog()['skins']:
        skins.setdefault(cfg['hero'], []).append(cfg['id'])
    for hero in heroes:
        hid = hero['id']
        old = previous.get(hid, {})
        hero['skins'] = skins[hid]
        for field in ('skin_id', 'battle_skin_id'):
            if old.get(field) in hero['skins']:
                hero[field] = old[field]
        equipped = old.get('equip_ids', [])
        hero['equip_ids'] = []
        for pos, prefab in enumerate(hero['equip_prefabs']):
            uid = equipped[pos] if pos < len(equipped) else 0
            item = equipment.get(uid, {})
            if uid in used_equips or item.get('hero_id') != hid or item.get('prefab_id') != prefab:
                uid, next_equip = next_equip, next_equip + 1
            hero['equip_ids'].append(uid)
            used_equips.add(uid)
        candidates = [s for s in servants if s['id'] == hero['servant_id'] and s['uid'] not in used_servants]
        servant = next((s for s in candidates if s['uid'] == old.get('servant_uid')),
                       candidates[0] if candidates else None)
        if servant is None:
            servant = {'uid': next_servant, 'id': hero['servant_id']}
            servants.append(servant)
            next_servant += 1
        servant.update(stage=5, is_locked=1)
        hero['servant_uid'] = servant['uid']
        used_servants.add(servant['uid'])
        # 旧的跃迁选择会覆盖协议中的满级推荐配置。
        user.get('hero_preferences', {}).get(str(hid), {}).pop('exclusive_skill_list', None)
    playable = {h['id'] for h in heroes}
    for item in equipment.values():
        if item.get('hero_id') in playable:
            item['hero_id'] = 0
    generated = decode_message(13009, get_bridge().encode_sc_13009(heroes), 'sc')['equip_list']
    equipment.update({e['equip_id']: e for e in generated})
    user.update(heroes=heroes, equipment=list(equipment.values()), equipment_initialized=True,
                next_equip_uid=next_equip, servants=servants, next_servant_uid=next_servant)
    user['owned_skins'] = sorted(set(user.get('owned_skins', [])) | {s for h in heroes for s in h['skins']})
    unlock_scenes(user)


def unlock_scenes(user):
    """补齐全部永久场景及配置视角，保留已选择的场景和有效视角。"""
    catalog = unlock_catalog()
    decorations = user.setdefault('unlocked_decorations', {})
    decorations['poster_background_list'] = sorted(set(decorations.get('poster_background_list', [])) | set(catalog['scenes']))
    rows = user.setdefault('scene_views', [])
    by_scene = {row['poster_background_id']: row for row in rows}
    for cfg in catalog['views']:
        scene, view = cfg['scene_id'], cfg['view']
        if scene not in by_scene:
            row = {'poster_background_id': scene, 'sub_background_list': [], 'current_sub_background': 0}
            by_scene[scene] = row
            rows.append(row)
        row = by_scene[scene]
        row['sub_background_list'] = sorted(set(row['sub_background_list']) | {view})


def unlock_developer(user):
    """一次迁移补齐实际库存，保留玩家选中的装饰、编队和已有钥从实例。"""
    if user.get('uid') != 10001 and user.get('account') != 'Developer':
        return
    if user.get('unlock_version') == 3:
        return
    catalog = unlock_catalog()
    user['heroes'] = build_max_heroes(user.get('heroes'))
    heroes = {h['id']: h for h in user['heroes']}
    for skin in catalog['skins']:
        if skin['hero'] in heroes and skin['id'] not in heroes[skin['hero']]['skins']:
            heroes[skin['hero']]['skins'].append(skin['id'])
    inventory = servant_data(user)['servant_list']
    owned = {s['id'] for s in inventory}
    next_uid = max((s['uid'] for s in inventory), default=0) + 1
    for item in catalog['servants']:
        if item not in owned:
            inventory.append({'uid': next_uid, 'id': item, 'stage': 5, 'is_locked': 0})
            next_uid += 1
    user['servants'] = inventory
    user['next_servant_uid'] = max(next_uid, user.get('next_servant_uid', 1))
    frames = user.setdefault('unlocked_frames', [])
    decorations = user.setdefault('unlocked_decorations', {})
    for item, cfg in item_catalog().items():
        if cfg['type'] == 12:
            ids = frames
        elif cfg['type'] in DECORATION_FIELDS and cfg['type'] != 21:
            ids = decorations.setdefault(DECORATION_FIELDS[cfg['type']], [])
        else:
            continue
        if item not in ids:
            ids.append(item)
    # 场景 DLC 尚未齐备，暂缓自动扩展背景和额外视角，避免登录触发下载。
    user['unlock_version'] = 3


def illustrated_data(user):
    """以真实钥从库存补齐图鉴，个人主页解锁计数与背包保持一致。"""
    data = deepcopy(user.get('illustrated', {}))
    rows = data.setdefault('servant_info', [])
    owned = {r['id'] for r in rows}
    for servant in servant_data(user)['servant_list']:
        if servant['id'] not in owned:
            rows.append({'id': servant['id'], 'is_view': 1})
            owned.add(servant['id'])
    return data


def scene_view_data(user):
    """初始化皮肤对应场景的额外视角及玩家所选视角。"""
    return {'sub_poster_background_list': deepcopy(user.get('scene_views', []))}


def read_illustrated(user, request):
    """只记录已初始化图鉴条目的阅读状态。"""
    fields = {2: 'enemy_info', 3: 'servant_info', 4: 'equip_info', 5: 'plot_info', 6: 'inbetweening_info', 7: 'affix_info'}
    field = fields.get(request['type'])
    data = illustrated_data(user)
    row = next((r for r in data.get(field, []) if r.get('id', r.get('suit')) == request['id']), None)
    if not row:
        raise ValueError('图鉴条目未解锁')
    row['is_view'] = 1
    user['illustrated'] = data
    return {'result': 0}
