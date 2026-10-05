"""读取探测池、奖品、消耗和公开概率说明，保留客户端编号转换关系。"""

from functools import lru_cache
import re

from gameplay_protocol import read_client_data


@lru_cache(maxsize=1)
def draw_catalog() -> dict:
    """读取当前版本配置；概率使用客户端说明中的基础出率。"""
    data = read_client_data('''(function()
        local r={pools={},items={},settings={},activities={},bonuses={},pieces={},rates={},heroes={},servants={},rules={}}
        for name,key in pairs({DrawPoolCfg='pools',DrawItemCfg='items',DrawSettingCfg='settings',ActivityDrawPoolCfg='activities',ActivityDrawBonusCfg='bonuses'}) do
            local c=require(name)
            for _,id in ipairs(c.all or {}) do r[key][#r[key]+1]=c[id] end
            if not c.all then
                for id,v in pairs(c) do if type(id)=='number' and type(v)=='table' then r[key][#r[key]+1]=v end end
            end
        end
        local tips=require('TipsCfg')
        for _,key in ipairs({'S','A','B','C','FIVE_WEAPON','FOUR_WEAPON','THREE_WEAPON'}) do
            r.rates[key]=tips[tips.get_id_list_by_define['DRAW_POOL_PROBABILITY_'..key..'_2']].desc
        end
        local g=require('GameSetting')
        for _,key in ipairs({'draw_num_max','draw_ssr_lucky_num_first_time','draw_ssr_lucky_num_beginner','return_draw_ssr_lucky_num_beginner','currency_for_draw','unlock_hero_need'}) do r.rules[key]=g[key].value end
        local items=require('ItemCfg');local items2=require('ItemCfg2')
        local seen={}
        for _,id in ipairs(require('DrawItemCfg').all) do
            local item=require('DrawItemCfg')[id].item_id
            if not seen[item] then
                seen[item]=true
                local cfg=items[item] or items2[item]
                if cfg.type==2 then r.heroes[tostring(item)]=require('HeroCfg')[item]
                elseif cfg.type==9 then r.servants[tostring(item)]=require('WeaponServantCfg')[item] end
            end
        end
        for _,name in ipairs({'ItemCfg','ItemCfg2'}) do
            local c=require(name)
            for _,id in ipairs(c.all or {}) do
                if c[id] and c[id].type==3 then r.pieces[tostring(tonumber(c[id].icon))]=id end
            end
        end
        local valid={}
        for _,a in ipairs(r.activities) do
            local cfg=require('ActivityCfg')[a.id]
            if cfg then
                a.theme=cfg.activity_theme;a.template=cfg.activity_template
                valid[#valid+1]=a
            end
        end
        r.activities=valid
        return r
    end)()''')
    for name in ('pools', 'items', 'settings', 'activities', 'bonuses'):
        data[name] = {row['activity_id' if name == 'bonuses' else 'id']: row for row in data[name]}
    data['rates'] = {key: float(re.search(r'(\d+(?:\.\d+)?)%', text)[1]) / 100
                     for key, text in data['rates'].items()}
    return data


def draw_activities() -> list[dict]:
    """补齐客户端常驻钥从、自选标准和新人定向池的活动入口。"""
    catalog = draw_catalog()
    standard = max((p['id'] for p in catalog['pools'].values() if p['pool_type'] == 1), default=10001)
    return [{'activity_id': a['id'], 'theme': a['theme'], 'template': a['template'],
             'state': 1, 'sub_activity_id_list': []}
            for a in catalog['activities'].values()
            if any(p in (10002, standard, 3000801) for p in a['config_list'])]


def available_draw_pools() -> set[int]:
    """只接受客户端当前开放活动里的探测池。"""
    from activity_data import build_available_activities
    opened = {a['activity_id'] for a in build_available_activities() if a['state'] == 1}
    return {pool for a in draw_catalog()['activities'].values() if a['id'] in opened for pool in a['config_list']}


def draw_group(pool: dict) -> str:
    """普通与旧新人池共用进度；精准扩充、锚定和钥从分别继承保底。"""
    kind = pool['pool_type']
    return str(1 if kind == 5 else kind)


def pool_details(pool: dict, selected: int) -> dict:
    """按 DrawSettingCfg 返回 DrawItemCfg 编号，供客户端查询概率与名单。"""
    catalog = draw_catalog()
    groups = catalog['settings'][pool['pool_draw_range_type']]['pool_id']
    rows = [r for r in catalog['items'].values() if r['pool_id'] in groups]
    optional = pool['optional_lists'] if isinstance(pool['optional_lists'], list) else []
    fixed = pool['unoption_up_items']
    s_up = [selected] if selected else (fixed[0] if isinstance(fixed[0], list) else [])
    a_up = fixed[1] if isinstance(fixed[1], list) else []
    if pool['pool_type'] == 2 and selected:
        race = catalog['servants'][str(selected)]['race']
        a_up = [r['item_id'] for r in rows if r['pool_id'] == 1002 and catalog['servants'][str(r['item_id'])]['race'] == race]
    # 当前定向 S 不一定在默认候选组中，仍必须有有效 DrawItemCfg 描述。
    for item in s_up + a_up:
        if not any(r['item_id'] == item for r in rows):
            row = next((r for r in catalog['items'].values() if r['item_id'] == item), None)
            if row is None:
                raise ValueError('自选奖品缺少探测描述')
            rows.append(row)
    result = {'s_up_probability': 100 if pool['pool_type'] in (2, 8, 9) else 55 if pool['pool_type'] == 6 else 50,
              'a_up_probability': 100 if pool['pool_type'] == 2 else 90,
              's_up_item': [], 's_other_item': [], 'a_up_item': [], 'a_other_item': [], 'b_item': []}
    seen = set()
    for row in rows:
        item = row['item_id']
        if item in seen:
            continue
        seen.add(item)
        group = row['pool_id']
        if group in (201, 1002):
            key = 'a_up_item' if item in a_up else 'a_other_item'
        elif group in (301, 1003):
            key = 'b_item'
        else:
            key = 's_up_item' if item in s_up else 's_other_item'
        result[key].append(row['id'])
    if not s_up and optional:
        result['s_up_probability'] = 0
    return result
