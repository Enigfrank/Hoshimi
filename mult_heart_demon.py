"""古远虚影入口初始化，使用当前客户端中已开放活动的配置。"""

from functools import lru_cache
import time

from activity_data import RESOURCE_ACTIVITIES
from gameplay_protocol import read_client_data, lua_value


@lru_cache(maxsize=1)
def current_edition() -> int:
    """选择本机开放且有玩法配置的一期，客户端仅支持一个当前期次。"""
    activities = [aid for aid, (_, template, _) in RESOURCE_ACTIVITIES.items() if template == 350]
    return read_client_data('''(function()
        local cfg=require('MultHeartDemonCfg')
        for _,id in ipairs(__ACTIVITIES__) do
            if cfg.get_id_list_by_activity_id[id] then return id end
        end
        error('古远虚影缺少有效活动配置')
    end)()'''.replace('__ACTIVITIES__', lua_value(activities)))


def mult_heart_demon_pushes() -> list[tuple]:
    """下发挑战阶段及两档成绩表，让客户端初始化默认试用队伍和返回栏。"""
    edition = current_edition()
    refresh = int(time.time()) + 5 * 365 * 86400
    return [(64031, {'activity_id': edition, 'refresh_time': [refresh]}),
            (75017, {'open_edition': edition, 'challenge_stage': 0, 'info_list': [],
                     'max_score_list': [{'difficulty': difficulty, 'max_score': 0} for difficulty in (1, 2)]})]
