"""活动皮肤奖池、公开权重、重复兑换及当前资源入口。"""

from functools import lru_cache
import json
import re

from config import STREAMING_ASSETS_DIR
from gameplay_protocol import read_client_data


@lru_cache(maxsize=1)
def skin_catalog() -> dict:
    """读取皮肤池配置，以公开说明匹配核心奖品权重，避免猜测奖品顺序。"""
    data = read_client_data('''(function()
        local r={pools={},drops={},mains={},stories={},items={},activities={}}
        for name,key in pairs({ActivityLimitedDrawPoolListCfg='pools',ActivityLimitedDrawPoolCfg='drops',ActivityLimitedSkinStoryCfg='stories'}) do
            local c=require(name);for _,id in ipairs(c.all) do r[key][#r[key]+1]=c[id] end
        end
        for _,name in ipairs({'T0SkinDrawCfg','WeddingSkinDrawCfg'}) do
            local c=require(name);for _,id in ipairs(c.all) do
                local v=c[id];v.oath=name=='WeddingSkinDrawCfg';r.mains[#r.mains+1]=v
            end
        end
        local function item(id)
            if r.items[tostring(id)] then return end
            local c=require('ItemCfg')[id] or require('ItemCfg2')[id]
            local skin=require('SkinCfg')[id]
            local decorate=require('ProfileDecorateItemCfg')[id]
            r.items[tostring(id)]={id=id,name=(c.type==8 and skin.name) or (decorate and decorate.name) or c.name,type=c.type,
                sub_type=c.sub_type,param=c.param,exchange=c.num_exchange_item or {},hero=skin and skin.hero}
            if c.type==5 and c.sub_type==501 then for _,v in ipairs(c.param) do item(v[1]) end end
        end
        for _,d in ipairs(r.drops) do for _,v in ipairs(d.reward) do item(v[1]) end end
        local seen={};local function activity(id)
            if seen[id] or id==0 then return end
            seen[id]=true;local c=assert(require('ActivityCfg')[id])
            r.activities[tostring(id)]={activity_id=id,theme=c.activity_theme,template=c.activity_template,
                state=1,sub_activity_id_list=c.sub_activity_list}
            for _,sub in ipairs(c.sub_activity_list) do activity(sub) end
        end
        for _,v in ipairs(r.mains) do activity(v.activityId) end
        return r
    end)()''')
    data['pools'] = {p['pool_id']: p for p in data['pools']}
    data['drops'] = {d['id']: d for d in data['drops']}
    for pool in data['pools'].values():
        text = re.sub(r'<[^>]*>', '', pool['detail_note'])
        weights = re.findall(r'「([^」]+)」\s*(\d+)\s*(?=\n|$)', text)
        entries = [d for d in data['drops'].values() if d['pool_id'] == pool['pool_id']]
        for drop in entries:
            drop['weight'] = 1
            if drop['minimum_guarantee'] != 2:
                continue
            item = data['items'][str(drop['reward'][0][0])]
            name = item['name']
            if item['type'] == 5 and item['sub_type'] == 501:
                name = data['items'][str(item['param'][0][0])]['name']
            matches = [int(w) for label, w in weights if label == name or label.startswith(name + 'x')]
            if not matches:
                raise ValueError(f"皮肤池 {pool['pool_id']} 奖品 {drop['id']} 缺少公开权重")
            # 分阶段场景池在说明中分别列出同名奖品的两组权重。
            drop['weight'] = matches[min(drop['pool_stage'] - 1, len(matches) - 1)]
    return data


@lru_cache(maxsize=1)
def skin_activities() -> list[dict]:
    """各皮肤系统开放资源清单支持的最新一期，补齐任务、商店和剧情子活动。"""
    catalog = skin_catalog()
    manifest = json.loads((STREAMING_ASSETS_DIR / 'AssetHash_Info.bytes').read_bytes())
    bundles = {r.split('|')[0].lower() for r in manifest['assetHashList']}
    mains = []
    for oath in (False, True):
        supported = [m for m in catalog['mains'] if m['oath'] == oath
                     and '/'.join(m['mainUI'].lower().split('/')[:3]) + '.ys' in bundles]
        if supported:
            mains.append(max(supported, key=lambda m: m['activityId']))
    opened = set()

    def add(activity_id):
        """递归加入当前期次真实子活动，不改变历史主题父活动的结束状态。"""
        if activity_id in opened:
            return
        opened.add(activity_id)
        for sub in catalog['activities'][str(activity_id)]['sub_activity_id_list']:
            add(sub)

    for main in mains:
        add(main['activityId'])
    return [catalog['activities'][str(i)] for i in sorted(opened)]


def skin_pools() -> list[dict]:
    """返回当前开放的皮肤及场景奖池，不接受其他期次的伪造请求。"""
    opened = {a['activity_id'] for a in skin_activities()}
    return [p for p in skin_catalog()['pools'].values() if set(p['activity_id']) & opened]


def pool_main(pool_id: int) -> dict:
    """查找奖池的主活动及普通抽奖或翻牌规则。"""
    return next(m for m in skin_catalog()['mains'] if pool_id in m['poolList'])
