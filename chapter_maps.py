"""章节事件地图初始化与客户端移动、阅读和回溯请求的持久化。"""

from copy import deepcopy
from functools import lru_cache

from gameplay_protocol import read_client_data

CHAPTER_MAP_COMMANDS = {24030, 24062, 24064, 24066, 24068, 56002, 12100, 52014}


@lru_cache(maxsize=1)
def map_catalog():
    """读取真实地图、位置及事件 ID，避免接受任意编号。"""
    return read_client_data('''(function()
        local r={maps={},locations={},events={},legacy={}}
        for name,key in pairs({ChapterV2MapCfg='maps',ChapterV2MapLocationCfg='locations',ChapterV2MapEventCfg='events',ChapterMapCfg='legacy'}) do
            local c=require(name);for _,id in ipairs(c.all) do r[key][#r[key]+1]=c[id] end
        end
        return r
    end)()''')


def chapter_map_pushes(user):
    """恢复事件列表、当前地图位置、扫描记录及已处理红点。"""
    catalog = map_catalog()
    default = catalog['maps'][0]['default_location']
    return [(24061, deepcopy(user.get('chapter_v2', {'now_location': default, 'event_list': [], 'backtrack_list': []}))),
            (24029, deepcopy(user.get('chapter_map', {'map_info': [], 'detector_info': []}))),
            (56001, {'red_dot': user.get('read_red_dots', []), 'client_finished_red_dot': []})]


def chapter_map_request(user, command, request):
    """校验真实地图编号并保存请求产生的实际状态。"""
    if command == 12100:
        if not request['language'].strip() or len(request['language']) > 32:
            raise ValueError('语言选项无效')
        user['language'] = request['language']
        return {'result': 0}
    if command == 52014:
        from account_unlocks import read_illustrated
        return read_illustrated(user, request)
    if command == 56002:
        value = request['red_dot']
        if value <= 0:
            raise ValueError('红点编号无效')
        rows = user.setdefault('read_red_dots', [])
        if value not in rows:
            rows.append(value)
        return {'result': 0}
    catalog = map_catalog()
    if command == 24030:
        cfg = next((c for c in catalog['legacy'] if c['id'] == request['map_id']), None)
        if not cfg:
            raise ValueError('章节地图不存在')
        state = user.setdefault('chapter_map', {'map_info': [], 'detector_info': []})
        row = next((r for r in state['map_info'] if r['map_id'] == cfg['id']), None)
        if row is None:
            row = {'map_id': cfg['id'], 'scan_location_list': [], 'clue_location_list': [], 'event_list': [], 'clue_list': []}
            state['map_info'].append(row)
        row['scan_location_list'] = list(cfg['location_list'])
        return {'result': 0, 'location_id_list': row['scan_location_list']}
    state = user.setdefault('chapter_v2', {'now_location': catalog['maps'][0]['default_location'], 'event_list': [], 'backtrack_list': []})
    if command == 24064:
        location = request['new_location']
        if location not in {c['id'] for c in catalog['locations']}:
            raise ValueError('章节位置不存在')
        state['now_location'] = location
    elif command in (24062, 24066):
        event = request['event_id']
        cfg = next((c for c in catalog['events'] if c['id'] == event), None)
        if not cfg:
            raise ValueError('章节事件不存在')
        if command == 24062:
            if event not in state['event_list']:
                state['event_list'].append(event)
        else:
            if event not in state['event_list']:
                raise ValueError('事件尚未完成，不能回溯')
            location = next(c for c in catalog['locations'] if c['id'] == cfg['location'])
            state['backtrack_list'] = [r for r in state['backtrack_list'] if r['map_id'] != location['map']]
            state['backtrack_list'].append({'map_id': location['map'], 'start_event': event, 'backtrack_event_list': []})
    else:
        if request['map_id'] not in {c['id'] for c in catalog['maps']}:
            raise ValueError('章节地图不存在')
        state['backtrack_list'] = [r for r in state['backtrack_list'] if r['map_id'] != request['map_id']]
    return {'result': 0}
