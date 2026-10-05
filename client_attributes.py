"""在独立 Lua 环境中执行客户端原始属性公式，计算多维模板生命值。"""

from config import LUA_SRC_DIR
from gameplay_protocol import lua_value, read_client_data


def polyhedron_attributes(template: int, astrolabes: list, effects: list, differences: list, artifacts: int) -> list:
    """复用原始模板、刻印和属性函数；UI 类型仅提供不参与属性计算的占位值。"""
    root = lua_value(str(LUA_SRC_DIR).replace('\\', '/'))
    return read_client_data(f'''(function()
        local env={{}}
        setmetatable(env,{{__index=function(t,k)
            if k:match('Cfg%d*$') or k=='GameSetting' or k=='GameLevelSetting' then
                local v=require(k); rawset(t,k,v); return v
            end
            return _G[k]
        end}})
        local function vector(...) return {{...}} end
        env.Color=setmetatable({{New=vector,blue={{}},magenta={{}},white={{}}}},
            {{__call=function(_,...) return vector(...) end}})
        env.Vector3=setmetatable({{New=vector}},{{__call=function(_,...) return vector(...) end}})
        env.import=function(name)
            if name=='bit' then return require('bit') end
            return {{New=function() return {{}} end}}
        end
        env.clone=function(o) local r={{}};for k,v in pairs(o) do r[k]=v end;return r end
        env.table=env.clone(table)
        env.table.indexof=function(t,v) for i,c in ipairs(t) do if c==v then return i end end end
        env.table.isEmpty=function(t) return next(t)==nil end
        env.table.insertto=function(t,from) for _,v in ipairs(from) do t[#t+1]=v end end
        env.class=function(name,super)
            local c={{super=super}};c.__index=c;setmetatable(c,{{__index=super}})
            c.New=function(...)
                local o=setmetatable({{}},c);if o.Ctor then o:Ctor(...) end;return o
            end
            return c
        end
        env.singletonClass=env.class
        env.LvTools={{LevelToExp=function(level) return env.GameLevelSetting[level].hero_lv_exp_sum end}}
        local function load(name)
            local f=assert(loadfile({root}..'/'..name..'.lua'));setfenv(f,env)
            local result=f();if result then env[name]=result end
        end
        for _,name in ipairs({{'HeroConst','HeroTools','EquipTools','WeaponTools','BattlePowerTools',
            'EquipData','BaseHeroDataTemplate','TemplateHeroDataTemplate'}}) do load(name) end
        local cfg=env.HeroStarUpTemplateCfg
        local star=env.clone(cfg);star.template_dic={{}};env.HeroStarUpTemplateCfg=star
        for template,ids in pairs(cfg.get_id_list_by_template) do
            local kinds={{}};star.template_dic[template]=kinds
            for _,id in ipairs(ids) do
                local row=cfg[id];local kind=env.HeroStarSkillCfg[row.skill_id].type
                kinds[kind]=kinds[kind] or {{stage_dic={{}},stage_list={{}}}}
                kinds[kind].stage_dic[row.stage]=row.skill_id
                kinds[kind].stage_list[#kinds[kind].stage_list+1]=row.stage
            end
            for _,kind in pairs(kinds) do table.sort(kind.stage_list) end
        end
        local equip=env.clone(env.EquipCfg)
        setmetatable(equip,{{__index=env.EquipCfg2}});env.EquipCfg=equip
        local c=env.HeroStandardSystemCfg[{int(template)}]
        local h=env.TemplateHeroDataTemplate.New(c.hero_id);h:Init(c)
        h.using_astrolabe={lua_value(astrolabes)}
        local extra={{}}
        for _,row in ipairs({lua_value(effects)}) do
            local e=env.PolyhedronEffectCfg[row.id]
            if e.moment==2 and (e.action==2 or e.action==5) then
                for _,p in ipairs(e.params) do
                    extra[p[1]]=env.HeroTools.AttributeAdd(p[1],extra[p[1]],p[2]*(e.action==5 and {int(artifacts)} or 1))
                end
            end
        end
        for _,row in ipairs({lua_value(differences)}) do
            extra[row.id]=env.HeroTools.AttributeAdd(row.id,extra[row.id],row.value)
        end
        local poly={{CalPolyhedronAttribute=function() return extra end}}
        return env.GetPolyhedronHeroPracticalAttr(poly,h,h.equip_list,c.id)
    end)()''')
