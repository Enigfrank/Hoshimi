"""将大厅角色和试用模板转换为客户端实际读取的战斗属性。"""

from copy import deepcopy
from functools import lru_cache

from gameplay_protocol import read_client_data


@lru_cache(maxsize=100)
def hero_experience(level: int) -> int:
    """按客户端逐级经验表计算累计经验，供战斗模板恢复真实等级。"""
    return read_client_data(f"(function() local c=require('GameLevelSetting'); local n=0; "
                            f"for i=1,{int(level)-1} do n=n+c[i].hero_level_exp1 end return n end)()")


def owned_battle_hero(info: dict, equipment: list, servants: list) -> dict:
    """复制玩家当前配装并携带钥从实体、信赖关系和完整等级经验。"""
    base = deepcopy(info['hero_base_info'])
    base['exp'] = hero_experience(base['level'])
    servant = next((s for s in servants if s['uid'] == base['weapon'].get('servant_uid')), None)
    base['servant'] = {'id': servant['id'], 'stage': servant['stage']} if servant else {'id': 0, 'stage': 0}
    equipped = {e['equip_id'] for e in info['equip'] if e['equip_id']}
    equips = []
    for source in equipment:
        if source['equip_id'] not in equipped:
            continue
        equip = deepcopy(source)
        equip.pop('race_preview', None)
        for slot in equip['enchant_slot_list']:
            slot.pop('preview_list', None)
        equips.append(equip)
    return {'hero_base_info': base, 'hero_type': 1, 'equip_list': equips,
            'dorm_level': 1, 'trust': deepcopy(info['trust'])}


def trial_battle_hero(template_id: int) -> dict:
    """试用角色严格使用指定模板的属性与刻印，不借用玩家满养成数据。"""
    return read_client_data(f'''(function()
        local c=require('HeroStandardSystemCfg')[{int(template_id)}]
        if not c then return {{}} end
        local h=require('HeroCfg')[c.hero_id]
        local base={{id=c.id,level=c.hero_lv,exp=0,star=c.star_lv,break_level=c.hero_break,
            using_skin=c.skin_id,battle_using_skin=c.skin_id,weapon_module_level=c.weapon_module_level,
            weapon={{exp=require('GameLevelSetting')[c.weapon_level].weapon_lv_exp_sum,
                breakthrough=c.weapon_break}},servant={{id=c.weapon_key,stage=c.weapon_stage}},
            skill={{}},skill_intensify_attribute_list={{}},exclusive_skill_list={{}},
            using_astrolabe=type(c.astrolabe_id)=='table' and c.astrolabe_id or {{}}}}
        for i=1,c.hero_lv-1 do base.exp=base.exp+require('GameLevelSetting')[i].hero_level_exp1 end
        for _,id in ipairs(h.skills) do
            base.skill[#base.skill+1]={{skill_id=id,skill_level=id==h.avoid[1] and 1 or c.skill_lv}}
        end
        for i,lv in ipairs(type(c.skill_element)=='table' and c.skill_element or {{}}) do
            base.skill_intensify_attribute_list[#base.skill_intensify_attribute_list+1]={{index=i,level=lv}}
        end
        for i,ids in ipairs(type(c.equip_exclusive_id_list)=='table' and c.equip_exclusive_id_list or {{}}) do
            local slot={{slot_id=i,talent_points=6,skill_list={{}}}}
            for j,id in ipairs(ids) do slot.skill_list[#slot.skill_list+1]={{skill_id=id,
                skill_level=c.equip_exclusive_lv_list[i][j]}} end
            base.exclusive_skill_list[#base.exclusive_skill_list+1]=slot
        end
        local equips={{}}
        for i,id in ipairs(type(c.equip_list)=='table' and c.equip_list or {{}}) do
            local cfg=require('EquipCfg')[id] or require('EquipCfg2')[id]
            local e={{equip_id=i,prefab_id=id,hero_id=c.id,
                exp=require('EquipExpCfg')[c.equip_lv]['exp_sum_'..cfg.starlevel],
                race=c.hero_id,now_break_level=math.max(0,c.break_lv-1),enchant_slot_list={{}}}}
            for j,pool in ipairs((c.equip_pool_list or {{}})[i] or {{}}) do
                local effects={{}}
                for _,skill in ipairs(require('EquipSkillPoolCfg')[pool].skill_id) do
                    effects[#effects+1]={{id=skill[1],level=skill[2]}}
                end
                e.enchant_slot_list[#e.enchant_slot_list+1]={{id=j,effect_list=effects}}
            end
            equips[#equips+1]=e
        end
        return {{hero_base_info=base,hero_type=2,equip_list=equips,dorm_level=0,
            trust={{level=0,exp=0,mood=1,relation={{tier_list={{{{tier=1,upgrade_complete_list={{}}}}}}}}}}}}
    end)()''')
