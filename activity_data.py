"""本机可加载的主题活动、主线解锁排期与常驻入口。"""

from runtime_data import load_runtime_table

from functools import lru_cache
import time

RESOURCE_ACTIVITY_THEME = 44

# activity_id: (theme, template, sub_activity_ids)
RESOURCE_ACTIVITIES = load_runtime_table("RESOURCE_ACTIVITIES", tuples=True)

# 常驻玩法在原主题活动结束后开放，父记录必须使用已结束的排期。
RESIDENT_ACTIVITY_MAINS = load_runtime_table("RESIDENT_ACTIVITY_MAINS", tuples=True)

@lru_cache(maxsize=1)
def chapter_activity_catalog() -> list[dict]:
    """只读取主线解锁依赖及已核对页面资源的常驻玩法，补齐其子活动。"""
    from gameplay_protocol import read_client_data
    return read_client_data('''(function()
        local result={};local seen={};local activities=require('ActivityCfg')
        local function add(id)
            if id==0 or seen[id] then return end
            local c=assert(activities[id], '活动配置缺失: '..id)
            seen[id]=true
            result[#result+1]={activity_id=id,theme=c.activity_theme,
                template=c.activity_template,sub_activity_id_list=c.sub_activity_list}
            for _,sub in ipairs(c.sub_activity_list) do add(sub) end
        end
        local chapters=require('ChapterCfg')
        for _,id in ipairs(chapters.all) do
            if chapters[id].type==1 then
                add(chapters[id].activity_id);add(chapters[id].unlock_activity_id)
            end
        end
        local maps=require('ChapterMapCfg')
        for _,id in ipairs(maps.all) do
            if chapters[maps[id].chapter_id] and chapters[maps[id].chapter_id].type==1 then
                add(maps[id].activity_id)
            end
        end
        local clients=require('ChapterClientCfg')
        for _,id in ipairs(clients.get_id_list_by_toggle[8]) do add(clients[id].activity_id) end
        add(require('ActivityConst').SIGN)
        return result
    end)()''')


def build_available_activities() -> list[dict]:
    """开放主线及常驻子活动，原主题父记录保持结束以解锁常驻页签。"""
    now = int(time.time())
    result = {}
    for aid, (theme, template, subs) in RESOURCE_ACTIVITIES.items():
        result[aid] = {"activity_id": aid, "theme": theme, "template": template,
                       "state": 1, "sub_activity_id_list": list(subs)}
    for cfg in chapter_activity_catalog():
        result[cfg['activity_id']] = {**cfg, 'state': 1}
    for aid, (theme, template, subs) in RESIDENT_ACTIVITY_MAINS.items():
        result[aid] = {"activity_id": aid, "theme": theme, "template": template,
                       "state": 0, "start_time": now - 30 * 86400, "stop_time": now - 86400,
                       "sub_activity_id_list": list(subs)}
    from gacha_catalog import draw_activities
    for cfg in draw_activities():
        result[cfg['activity_id']] = cfg
    from skin_draw_catalog import skin_activities
    for cfg in skin_activities():
        result[cfg['activity_id']] = cfg
    return list(result.values())
