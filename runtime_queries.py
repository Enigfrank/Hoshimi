"""本机配置查询规则；只保存查询代码，不附带查询结果。"""

TABLE_QUERY = r'''(function()
    local function array() return setmetatable({}, {json_array=true}) end
    local function ids(t)
        local r=array();for k in pairs(t) do if type(k)=='number' then r[#r+1]=k end end
        table.sort(r);return r
    end
    local r={}
    r.ALL_GUIDE_IDS=ids(require('GuideBaseCfg'))
    r.ALL_WEAK_GUIDE_IDS=ids(require('GuideWeakCfg'))
    r.SYSTEM_IDS=ids(require('SystemCfg'))
    r.STAGE_IDS=array()
    local chapters=require('ChapterCfg')
    for _,id in ipairs(chapters.all) do
        if chapters[id].type==1 then
            for _,sid in ipairs(chapters[id].section_id_list) do r.STAGE_IDS[#r.STAGE_IDS+1]=sid end
        end
    end
    table.sort(r.STAGE_IDS)
    r.SHOP_GOODS_NOREFRESH={}
    for _,name in ipairs({'ShopCfg','ShopCfg2','ShopCfg3','ShopCfg4'}) do
        for _,g in pairs(require(name)) do
            if type(g)=='table' and g.goods_id and g.shop_id and g.shop_refresh~=2 then
                local key=tostring(g.shop_id)
                r.SHOP_GOODS_NOREFRESH[key]=r.SHOP_GOODS_NOREFRESH[key] or array()
                table.insert(r.SHOP_GOODS_NOREFRESH[key],g.goods_id)
            end
        end
    end
    for key,values in pairs(r.SHOP_GOODS_NOREFRESH) do
        table.sort(values);local unique=array();local prev=nil
        for _,v in ipairs(values) do if prev~=v then unique[#unique+1]=v;prev=v end end
        r.SHOP_GOODS_NOREFRESH[key]=unique
    end
    local items={};local currency={};local labels={};r.ALL_CURRENCY_IDS=array()
    for name,c in pairs(require('CurrencyIdMapCfg')) do
        if type(c)=='table' and c.item_id then
            currency[c.item_id]=true;labels[c.item_id]=name
            r.ALL_CURRENCY_IDS[#r.ALL_CURRENCY_IDS+1]=c.item_id
        end
    end
    table.sort(r.ALL_CURRENCY_IDS)
    for _,name in ipairs({'ItemCfg','ItemCfg2'}) do
        local cfg=require(name)
        for _,id in ipairs(cfg.all) do
            if cfg[id] then
                items[id]=cfg[id]
                if cfg[id].type==1 then currency[id]=true end
            end
        end
    end
    r.CURRENCY_DEFINITIONS={}
    for id in pairs(currency) do r.CURRENCY_DEFINITIONS[tostring(id)]={(items[id] or {}).type or 0,labels[id] or ''} end
    r.SUPPLY_DEFINITIONS={}
    local supply_shops={[5]=3,[6]=42,[8]=16,[14]=17,[21]=15}
    local descriptions=require('RechargeShopDescriptionCfg')
    for _,id in ipairs(descriptions.all) do
        local kind=descriptions[id].type;local sid=supply_shops[kind]
        if sid then r.SUPPLY_DEFINITIONS[tostring(id)]={kind,sid} end
    end
    r.HERO_DEFINITIONS={};r.HERO_LOADOUTS={}
    local heroes=require('HeroCfg');local skins=require('SkinCfg')
    local astrolabes=require('HeroAstrolabeCfg');local modules=require('WeaponModuleCfg')
    local recommends=require('EquipRecommendCfg');local servants=require('WeaponServantCfg')
    for _,id in ipairs(heroes.all) do
        local c=heroes[id];local rec=recommends[id]
        if c.private==0 and rec then
            local owned=array();local astro=array();local servant=0
            for _,sid in ipairs(skins.get_id_list_by_hero[id] or {}) do owned[#owned+1]=sid end
            for _,aid in ipairs(astrolabes.all) do if math.floor(aid/10000)==id then astro[#astro+1]=aid end end
            for _,sid in ipairs(servants.all) do
                local s=servants[sid]
                if s.starlevel==5 then
                    for _,effect in ipairs(s.effect) do if math.floor(effect/100)==id then servant=sid end end
                end
            end
            table.sort(astro)
            r.HERO_DEFINITIONS[tostring(id)]={c.skills,owned,astro,modules[id] and #modules[id].skill or 0,servant}
            local enchants=array()
            for i=1,math.min(4,#c.recommend_equip_skill[1]) do enchants[#enchants+1]=c.recommend_equip_skill[1][i] end
            r.HERO_LOADOUTS[tostring(id)]={rec.equip_list3,c.recommend_equip_warp,enchants}
        end
    end
    r.RESOURCE_ACTIVITIES={};r.RESIDENT_ACTIVITY_MAINS={}
    local activities=require('ActivityCfg')
    local resident={};local clients=require('ChapterClientCfg')
    for _,id in ipairs(clients.get_id_list_by_toggle[8]) do resident[clients[id].activity_id]=true end
    for _,id in ipairs(activities.all) do
        local c=activities[id]
        if c.activity_theme==44 then
            local subs=array();for _,sub in ipairs(c.sub_activity_list) do subs[#subs+1]=sub end
            r.RESOURCE_ACTIVITIES[tostring(id)]={c.activity_theme,c.activity_template,subs}
        end
        if c.activity_template==100 then
            for _,sub in ipairs(c.sub_activity_list) do
                if resident[sub] then r.RESIDENT_ACTIVITY_MAINS[tostring(id)]={c.activity_theme,c.activity_template,c.sub_activity_list} end
            end
        end
    end
    return r
end)()'''

DESCRIPTOR_QUERY = r'''(function()
    local r={}
    local types={'double','float','int64','uint64','int32','fixed64','fixed32','bool','string','group','message','bytes','uint32','enum','sfixed32','sfixed64','sint32','sint64'}
    local labels={'optional','required','repeated'}
    for _,name in ipairs(MODULE_NAMES) do
        for key,v in pairs(require(name)) do
            if type(v)=='table' and v.fields and v.name then
                local fields=setmetatable({}, {json_array=true})
                for _,f in ipairs(v.fields) do
                    local sub=f.message_type or f.enum_type
                    local default=f.default_value
                    if type(default)~='number' and type(default)~='boolean' and type(default)~='string' then default=nil end
                    fields[#fields+1]={tag=f.number,name=f.name,type=types[f.type],type_id=f.type,
                        label=labels[f.label],label_id=f.label,sub_type=sub and sub.name,
                        sub_full_name=sub and sub.full_name,default=default}
                end
                r[#r+1]={module=name,descriptor_key=key,name=v.name,full_name=v.full_name or '',fields=fields}
            end
        end
    end
    return r
end)()'''
