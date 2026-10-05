"""与客户端一致的北京时间业务日和刷新时刻。"""

from functools import lru_cache

from gameplay_protocol import read_client_data


@lru_cache(maxsize=1)
def refresh_hour() -> int:
    """使用本机 GameSetting 的每日刷新小时，当前版本为北京时间 05:00。"""
    return read_client_data("require('GameSetting').refresh_time1.value[1][1]")


def business_day(timestamp: int) -> int:
    """凌晨刷新之前仍属于上一业务日，避免签到和任务提前重置。"""
    return (timestamp + (8-refresh_hour())*3600)//86400
