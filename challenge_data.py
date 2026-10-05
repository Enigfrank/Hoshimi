"""挑战玩法的本地排期与初始化；关卡取自安装包配置。"""

from functools import lru_cache
import time

from gameplay_protocol import read_client_data
from polyhedron_game import polyhedron_data
from equip_exploration import exploration_pushes
from battle_progress import progress, tower_progress


@lru_cache(maxsize=1)
def challenge_catalog() -> dict:
    """提取挑战所需的配置，避免下发无效关卡或测试 ID。"""
    return read_client_data('''(function()
        local r={}
        local function rows(name)
            local c=require(name); local t={}
            for _,id in ipairs(c.all) do t[#t+1]=c[id] end
            return t
        end
        r.mythic=rows('MythicNormalCfg')
        r.mythic_stages=require('BattleMythicStageCfg').all
        r.mythic_affixes={}
        for _,id in ipairs({101,102,103}) do
            local affix=require('AffixTypeCfg')[id]
            assert(affix and affix.max_level>=1)
            r.mythic_affixes[#r.mythic_affixes+1]={id=id,level=1,type=0}
        end
        r.final=rows('MythicFinalCfg')
        r.boss=rows('BossChallengeCfg')
        r.boss_groups={}
        for _,area in ipairs(r.boss) do for _,id in ipairs(area.boss_list) do
            r.boss_groups[tostring(id)]=require('StageGroupCfg')[id].stage_list
        end end
        r.advance=rows('BossChallengeAdvanceCfg')
        r.advance_pool=rows('BossChallengeAdvancePoolCfg')
        r.seizure=require('BattleEquipSeizureStageCfg').all
        r.enchant=require('StageGroupCfg')[1].stage_list
        r.abyss=rows('AbyssCfg')
        r.core=rows('CoreVerificationInfoCfg')
        r.polyhedron=rows('PolyhedronHeroShelvesCfg')
        r.chess=rows('WarchessLevelCfg')
        r.rogue=rows('RogueTeamCfg')
        return r
    end)()''')


def enchantment_data(user: dict) -> dict:
    """下发联合特勤有效的三档关卡。"""
    return {'free_refreshed_times': 0, 'all_buy_refreshed_times': 0,
            'enchantment_battle_list': challenge_catalog()['enchant']}


def boss_data(user: dict) -> list[tuple]:
    """初始化梦境普通与扭曲模式，所选层级保存在账号中。"""
    c = challenge_catalog()
    area = (next((x for x in c['boss'] if x['level'][0] <= user.get('level', 1) <= x['level'][1]), c['boss'][0])
            if user.get('account_template') == 'normal' else next(x for x in c['boss'] if x['range_id'] == 4))
    advance = next(x for x in c['advance'] if x['type'] == 2)
    groups = []
    for group_id in area['boss_list'][:area['boss_nums']]:
        stages = c['boss_groups'][str(group_id)]
        completed = [s for s in stages if progress(user, 10, s).get('clear_times')]
        groups.append({'group_id': group_id, 'finish_stage': completed[-1] if completed else 0,
                       'unlock_timestamp': 0,
                       'used_heroes': sorted({h for s in completed for h in progress(user,10,s).get('last_heroes', [])}),
                       'last_heroes_cfg': user.get('boss_teams', {}).get(str(group_id), []),
                       'star_info': [{'stage_id': s, 'star_list': progress(user,10,s).get('stars', [])}
                                     for s in completed]})
    return [
        (45201, {'mode': user.get('boss_mode', 0), 'next_refresh_time': int(time.time()) + 7*86400,
                 'difficulty_list': [x['id'] for x in c['advance']
                                     if user.get('account_template') != 'normal' or x['open_condition'] <= user['level']]}),
        (45001, {'area_id': area['range_id'], 'use_times': 0,
                 'boss_challenge_list': groups, 'receive_star_list': user.get('boss_star_rewards', [])}),
        (45101, {'advance_id': advance['id'], 'boss_list': [
            {'id': x['id'], 'unlock_timestamp': 0, 'max_point': 0, 'diffculty_index': 1,
            **user.get('boss_affixes', {}).get(str(x['id']), {})}
            for x in c['advance_pool'][:advance['boss_nums']]]}),
    ]


def challenge_pushes(user: dict) -> list[tuple]:
    """初始化黑区、深阱、梦境、迭代和刻印挑战的页面依赖。"""
    c = challenge_catalog()
    refresh = int(time.time()) + 7*86400
    normal = next((x for x in c['mythic'] if x['id'] == user.get('mythic_difficulty', 1)), c['mythic'][0])
    final_id = user.get('mythic_final_difficulty', 1)
    final = next(x for x in c['final'] if x['id'] == final_id)
    runs = user.get('mythic_final_runs', {}).get(str(final_id), {})
    difficulties = []
    for x in c['mythic']:
        stages = c['mythic_stages']
        difficulties.append({'difficulty': x['id'],
                             'main_partition': {'partition': x['main_partition'], 'stage_id': stages[0]},
                             'sub_partition_list': [{'partition': id, 'stage_id': stages[(i+1) % len(stages)]}
                                                    for i, id in enumerate(x['sub_partition_list'])]})
    abyss = [x for x in c['abyss'] if x['activity_id'] == c['abyss'][0]['activity_id']]
    layers = []
    for x in abyss:
        layers.append({'layer_id': x['level'],
                       'stage_info_list': [{'stage_id': s[1], 'is_completed': bool(progress(user,1003,s[1]).get('clear_times'))}
                                           for s in x['stage_list'] if s[0] != 3],
                       'boss_stage_info_list': [{'stage_id': s[1], 'is_completed': bool(progress(user,1003,s[1]).get('clear_times')),
                                                'boss_hp_rate': 0 if progress(user,1003,s[1]).get('clear_times') else 10000}
                                                for s in x['stage_list'] if s[0] == 3]})
    initial = user.get('account_template') == 'normal'
    unlocked_mythic = ([c['mythic'][0]['id']] if initial else [x['id'] for x in c['mythic']] + [1001])
    unlocked_final = [c['final'][0]['id']] if initial else [x['id'] for x in c['final']]
    completed_layers = [x['level'] for x in abyss
                        if all(progress(user, 1003, s[1]).get('clear_times') for s in x['stage_list'])]
    history_layer = max(completed_layers, default=0) if initial else len(layers)
    return [
        (42001, enchantment_data(user)),
        *exploration_pushes(user),
        (35011, {'stage_id': c['seizure'][0], 'challenge_rate': 1,
                 'affix_info': {'refresh_timestamp': refresh}, 'refresh_timestamp': refresh}),
        (41001, tower_progress(user)),
        *boss_data(user),
        (44007, {'difficulty_list': difficulties, 'superiority_affix_list': c['mythic_affixes'],
                 'next_refresh_timestamp': refresh}),
        (44009, {'clear_partition_id_list': [int(key.split(':')[1])
                    for key, value in user.get('battle_progress', {}).items()
                    if key.startswith('11:') and value.get('clear_times')],
                 'main_partition_star_list': progress(user, 11, normal['main_partition']).get('stars', []),
                 'star_reward_provide_list': user.get('mythic_star_rewards', {}).get(str(normal['id']), [])}),
        (44019, {'open_difficulty_list': unlocked_mythic,
                 'difficulty': user.get('mythic_difficulty', 1), 'is_new_difficulty': False}),
        (44021, {'stage_list': [{'difficulty_id': x['id'], 'stage_id': [s[0] for s in x['stage_list']]}
                               for x in c['final']]}),
        (44023, {'difficulty_id_can_choose': unlocked_final, 'now_difficulty': final_id,
                 'is_new_difficulty': False, 'receive_reward': user.get('mythic_final_rewards', []),
                 'clear_list': user.get('mythic_final_cleared', []),
                 'challenge_info': [{'team_id': i, 'clear_state': int(all(s in runs.get(str(i), {}).get('stages', []) for s in stages)),
                                     'use_time': runs.get(str(i), {}).get('use_time', 0)}
                                    for i, stages in enumerate(final['stage_list'], 1)]}),
        (55001, {'activity_id': abyss[0]['activity_id'], 'is_back': False, 'history_max_layer': history_layer,
                 'last_version_max_unlock_layer': min(len(layers), history_layer + 1) if initial else len(layers), 'refresh_timestamp': refresh,
                 'layer_info_list': layers, 'got_layer_reward_list': user.get('abyss_rewards', [])}),
        (75009, {'now_cycle': c['core'][0]['cycle'], 'next_cycle': c['core'][0]['cycle'],
                 'refresh_timestamp': refresh, 'max_score_info': {},
                 'stage_info': [{'id': x['id'], 'sign': 1, 'min_time': progress(user,67,x['id'])['best_time']*1000}
                                for x in c['core'] if progress(user,67,x['id']).get('clear_times')]}),
        (18001, polyhedron_data(user)),
        *([(18005, {'end_info': user['polyhedron_settlement']})]
          if user.get('polyhedron', {}).get('game', {}).get('state') == 3 and user.get('polyhedron_settlement') else []),
        (49001, {'chess_map_list': [{'activity_id': 0, 'chapter': 0,
                                   'chapter_info': [{'chapter_id': x['id_level']} for x in c['chess']
                                                    if x['activity'] == 0]}]}),
        (49023, {'chess_open_info_list': [{'chapter_id': x['id_level'], 'timestamp': 0}
                                         for x in c['chess'] if x['activity'] == 0]}),
        (88305, {'template_id': c['rogue'][0]['id'], 'difficult': 0}),
    ]
