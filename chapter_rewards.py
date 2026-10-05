"""章节星数奖励与剧情档案阅读记录。"""

from battle_progress import story_progress
from battle_rewards import grant_rewards
from gameplay_protocol import read_client_data


def chapter_reward_data(user: dict) -> dict:
    """按真实领取记录初始化章节奖励，登录不会清空领取标记。"""
    return {'gain_list': [{'id': int(chapter), 'reward_list': [
        {'reward_order': order, 'is_received': 1} for order in orders]}
        for chapter, orders in user.get('chapter_rewards', {}).items()]}


def claim_chapter_reward(user: dict, request: dict) -> dict:
    """核对章节星数与配置奖励，拒绝重复领取和不存在的奖励档位。"""
    chapter, order = request['id'], request['treasure_id']
    cfg = read_client_data(f"require('ChapterCfg')[{int(chapter)}] or {{}}")
    claimed = user.setdefault('chapter_rewards', {}).setdefault(str(chapter), [])
    if not cfg or not 1 <= order <= len(cfg['star_need']) or order in claimed:
        raise ValueError('章节奖励不存在或已经领取')
    stages = {s['id']: s for s in story_progress(user)['user_chapter_list']}
    # 本地账号初始主线全解锁，已有三星种子与后续战斗结果使用相同入口数据。
    stars = sum(sum(bool(v) for v in stages.get(stage, {}).get('star_list', []))
                for stage in cfg['section_id_list'])
    if stars < cfg['star_need'][order-1]:
        raise ValueError('章节星数不足')
    rewards = [{'id': i, 'num': n} for i, n in cfg[('first_reward', 'second_reward', 'third_reward')[order-1]]]
    grant_rewards(user, rewards)
    claimed.append(order)
    return {'result': 0, 'reward_list': rewards}


def read_chapter_archive(user: dict, request: dict) -> dict:
    """只保存配置存在的剧情档案阅读标记。"""
    archive = request['archive_id']
    cfg = read_client_data(f"require('StageArchivesCollectCfg')[{int(archive)}] or {{}}")
    if not cfg:
        raise ValueError('剧情档案不存在')
    read = user.setdefault('chapter_archives', [])
    if archive not in read:
        read.append(archive)
    return {'result': 0}
