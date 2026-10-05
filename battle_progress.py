"""将实际通关记录转换为各常规玩法的初始化数据。"""

from functools import lru_cache

from gameplay_protocol import read_client_data


def progress(user: dict, stage_type: int, stage_id: int) -> dict:
    """读取指定玩法的实际次数、星数和最短耗时。"""
    return user.get('battle_progress', {}).get(f'{stage_type}:{stage_id}', {})


def stage_progress(user: dict, stage_type: int, stage_ids: list, unlocked: bool = False) -> list:
    """保留本地服原有解锁种子，并叠加后续真实战斗记录。"""
    result = []
    for stage_id in stage_ids:
        saved = progress(user, stage_type, stage_id)
        result.append({'id': stage_id, 'clear_times': max(int(unlocked), saved.get('clear_times', 0)),
                       'star_list': [int(i in saved.get('stars', [])) for i in (1, 2, 3)]})
    return result


@lru_cache(maxsize=1)
def progress_catalog() -> dict:
    """读取角色归属、历战章节和主线各关的有效星级条件。"""
    return read_client_data('''(function()
        local r={hero_teach={},tower={},story={}}
        local c=require('BattleHeroTeachStageCfg')
        for _,id in ipairs(c.all) do r.hero_teach[#r.hero_teach+1]=c[id] end
        c=require('ChapterCfg')
        local stages=require('BattleChapterStageCfg')
        local seen={}
        for _,id in ipairs(c.all) do
            if c[id].type==7 then r.tower[#r.tower+1]=c[id] end
            if c[id].type==1 then
                for _,stage in ipairs(c[id].section_id_list) do
                    if not seen[stage] then
                        seen[stage]=true
                        r.story[#r.story+1]={id=stage,star_count=#stages[stage].three_star_need}
                    end
                end
            end
        end
        return r
    end)()''')


def story_progress(user: dict) -> dict:
    """剧情全解锁；普通账号只恢复实际星级，旧体验账号保留配置星级。"""
    stages = {cfg['id']: cfg['star_count'] for cfg in progress_catalog()['story']}
    initial = user.get('account_template') == 'normal'
    rows = stage_progress(user, 1, list(stages), True)
    for row in rows:
        row['star_list'] = [int(i <= stages[row['id']] and (not initial or row['star_list'][i - 1]))
                            for i in (1, 2, 3)]
    for key, saved in user.get('battle_progress', {}).items():
        kind, stage_id = map(int, key.split(':'))
        if kind == 601:
            rows.append({'id': stage_id, 'clear_times': saved['clear_times'],
                         'star_list': [int(i in saved.get('stars', [])) for i in (1, 2, 3)]})
    return {'user_chapter_list': rows}


def hero_teaching(user: dict) -> dict:
    """按配置的教学角色下发通关记录。"""
    groups = {}
    for cfg in progress_catalog()['hero_teach']:
        saved = progress(user, 13, cfg['id'])
        if not saved.get('clear_times'):
            continue
        hero = cfg['hero_list'][0][0]
        groups.setdefault(hero, []).append({'id': cfg['id'], 'clear_times': saved['clear_times'],
                                            'star_list': len(saved['stars'])})
    return {'hero_teaching_list': [{'hero_id': h, 'stage_list': stages} for h, stages in groups.items()]}


def tower_progress(user: dict) -> dict:
    """历战轮回按章节保存当前已通关的最远关卡。"""
    result = []
    for cfg in progress_catalog()['tower']:
        cleared = [s for s in cfg['section_id_list'] if progress(user, 7, s).get('clear_times')]
        if cleared:
            result.append({'area': cfg['id'], 'stage': cleared[-1]})
    return {'info_list': result}
