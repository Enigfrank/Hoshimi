"""普通新账号与新获得角色的初始数据，不向既有账号补发解锁。"""

from functools import lru_cache

from gameplay_protocol import read_client_data


@lru_cache(maxsize=128)
def hero_initial_config(hero_id: int) -> dict:
    """读取有效角色的初始星级、技能和默认皮肤。"""
    return read_client_data(f"require('HeroCfg')[{int(hero_id)}] or {{}}")


def new_hero(hero_id: int) -> dict:
    """新角色从一级和配置初始星级开始，不附带神格、刻印或钥从。"""
    cfg = hero_initial_config(hero_id)
    if not cfg or cfg.get('private') == 1:
        raise ValueError('角色不是有效的可玩角色')
    return {'id': hero_id, 'level': 1, 'star': cfg['unlock_star'], 'break_level': 0,
            'skin_id': hero_id, 'battle_skin_id': hero_id, 'skins': [hero_id],
            'skills': cfg['skills'], 'skill_level': 1, 'skill_attr_level': 0,
            'astrolabes': [], 'using_astrolabes': [], 'module_level': 0,
            'weapon_exp': 0, 'weapon_break': 0, 'trust_level': 1,
            'equip_ids': [0] * 6, 'equip_prefabs': [], 'clear_times': 0}


def unlock_hero(user: dict, hero_id: int) -> dict:
    """获得角色时恢复已拥有的皮肤，并解锁其默认头像。"""
    hero = new_hero(hero_id)
    hero['skins'].extend(i for i in user.get('owned_skins', [])
                         if read_client_data(f"require('SkinCfg')[{int(i)}].hero") == hero_id
                         and i not in hero['skins'])
    user.setdefault('heroes', []).append(hero)
    portrait = read_client_data(f"require('SkinCfg')[{int(hero_id)}].portrait")
    icons = user.setdefault('unlocked_decorations', {}).setdefault('icon_list', [])
    if portrait not in icons:
        icons.append(portrait)
    return hero


@lru_cache(maxsize=1)
def initial_config() -> dict:
    """读取一级体力上限及客户端默认名片、看板和装饰。"""
    return read_client_data('''(function()
        local g=require('GameSetting')
        return {fatigue=require('GameLevelSetting')[1].fatigue_max,
                portrait=g.profile_avatar_default.value[1],frame=g.profile_avatar_frame_default.value[1],
                bubble=g.profile_chat_bubble_default.value[1],card=g.profile_business_card_default.value[1],
                sticker=g.sticker_background_default.value[1],scenes=g.home_sence_default.value,
                guides=require('GuideBaseCfg').all,weak_guides=require('GuideWeakCfg').all}
    end)()''')


def new_account_defaults() -> dict:
    """普通注册账号使用初始朝约、零库存和零星记录；剧情入口另行全解锁。"""
    cfg = initial_config()
    return {'account_template': 'normal', 'level': 1, 'exp': 0, 'total_exp': 0,
            'gold': 0, 'diamond': 0, 'stamina': cfg['fatigue'], 'draw_tickets': 0,
            'flower': 0, 'flower_ios': 0, 'flower_free': 0, 'currencies': {}, 'materials': {},
            'heroes': [new_hero(1084)], 'hero_pieces': {}, 'equipment': [], 'equipment_initialized': True,
            'servants': [], 'next_servant_uid': 1, 'battle_progress': {},
            'portrait': cfg['portrait'], 'icon_frame': cfg['frame'],
            'profile': {'sign': '', 'heroes': [1084], 'poster_girl': 1084,
                        'icon_list': [{'id': cfg['portrait'], 'lasted_time': 0, 'obtain_time': 0}],
                        'icon_frame_list': [{'id': cfg['frame'], 'lasted_time': 0}],
                        'chat_bubble_list': [{'id': cfg['bubble'], 'lasted_time': 0, 'obtain_time': 0}],
                        'chat_bubble': cfg['bubble'], 'information_background_id': cfg['card'],
                        'sticker_background': cfg['sticker']},
            'finished_guides': list(cfg['guides']), 'finished_weak_guides': list(cfg['weak_guides'])}


@lru_cache(maxsize=1)
def player_levels() -> list[dict]:
    """读取管理员等级经验阈值和升级体力奖励。"""
    return read_client_data('''(function() local r={}
        for i=1,require('GameSetting').user_level_max.value[1] do
            local c=require('GameLevelSetting')[i]
            r[#r+1]={exp=c.user_level_exp,fatigue=c.fatigue_upgrade_reward}
        end;return r end)()''')


def add_player_exp(user: dict, amount: int) -> None:
    """普通新账号通过实际经验成长，升级时发放配置体力，不改旧号模板。"""
    if user.get('account_template') != 'normal':
        return
    levels = player_levels()
    total = user.get('total_exp', 0) + amount
    user['total_exp'] = total
    previous, level = user['level'], 1
    while level < len(levels) and total >= levels[level - 1]['exp']:
        total -= levels[level - 1]['exp']
        level += 1
    user['level'], user['exp'] = level, total
    if level > previous:
        user['stamina'] += sum(levels[i - 1]['fatigue'] for i in range(previous + 1, level + 1))
        user.setdefault('currencies', {})['4'] = user['stamina']
