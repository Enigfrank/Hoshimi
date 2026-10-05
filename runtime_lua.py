"""本机准备工具的独立 Lua 读取器，不依赖服务端生成配置。"""

import ctypes
import json


class RuntimeLua:
    """使用用户本机 DLL 读取用户本机 Lua，退出时释放状态。"""

    def __init__(self, dll_path, lua_dir):
        """注册最少的 Lua API，加载本机脚本与 protobuf 扩展。"""
        self.dll = ctypes.CDLL(str(dll_path))
        signatures = {
            'luaL_newstate': ([], ctypes.c_void_p),
            'luaL_openlibs': ([ctypes.c_void_p], None),
            'luaopen_pb': ([ctypes.c_void_p], ctypes.c_int),
            'luaL_loadbuffer': ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p], ctypes.c_int),
            'lua_pcall': ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            'lua_tolstring': ([ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)], ctypes.c_void_p),
            'lua_settop': ([ctypes.c_void_p, ctypes.c_int], None),
            'lua_getfield': ([ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p], None),
            'lua_setfield': ([ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p], None),
            'lua_close': ([ctypes.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = args, result
        self.state = self.dll.luaL_newstate()
        if not self.state:
            raise RuntimeError('创建 Lua 状态失败')
        self.dll.luaL_openlibs(self.state)
        self.dll.lua_getfield(self.state, -10002, b'package')
        self.dll.lua_getfield(self.state, -1, b'loaded')
        self.dll.luaopen_pb(self.state)
        self.dll.lua_setfield(self.state, -2, b'pb')
        self.dll.lua_settop(self.state, 0)
        path = ''.join(f'\\{b:03d}' for b in str(lua_dir).replace('\\', '/').encode('utf-8'))
        self.evaluate(r'''(function()
            local base="''' + path + r'''/"
            table.insert(package.loaders, 1, function(name)
                local short=name:match('[^/]+$') or name
                for _,suffix in ipairs({'.lua','.lua.bytes'}) do
                    local f=io.open(base..short..suffix,'rb')
                    if f then f:close();return assert(loadfile(base..short..suffix)) end
                end
            end)
            function json_value(value)
                local kind=type(value)
                if kind=='nil' then return 'null' end
                if kind=='number' or kind=='boolean' then return tostring(value) end
                if kind=='string' then
                    return '"'..value:gsub('[%z\1-\31\\"]',function(c)
                        return string.format('\\u%04x',string.byte(c)) end)..'"'
                end
                local parts={}
                if #value>0 or (getmetatable(value) or {}).json_array then
                    for _,v in ipairs(value) do parts[#parts+1]=json_value(v) end
                    return '['..table.concat(parts,',')..']'
                end
                for k,v in pairs(value) do parts[#parts+1]=json_value(tostring(k))..':'..json_value(v) end
                return '{'..table.concat(parts,',')..'}'
            end
            return true
        end)()''')

    def evaluate(self, expression: str) -> bytes:
        """执行工具内固定表达式，清空栈后返回结果或错误。"""
        code = ('return ' + expression).encode('utf-8')
        try:
            error = self.dll.luaL_loadbuffer(self.state, code, len(code), b'hoshimi_prepare')
            if not error:
                error = self.dll.lua_pcall(self.state, 0, 1, 0)
            size = ctypes.c_size_t()
            ptr = self.dll.lua_tolstring(self.state, -1, ctypes.byref(size))
            value = ctypes.string_at(ptr, size.value) if ptr else b''
            if error:
                raise RuntimeError(value.decode('utf-8', errors='replace'))
            return value
        finally:
            self.dll.lua_settop(self.state, 0)

    def read(self, expression: str):
        """将查询值序列化后返回 Python 数据。"""
        return json.loads(self.evaluate('json_value(' + expression + ')'))

    def close(self) -> None:
        """释放本机 Lua 状态。"""
        if self.state:
            self.dll.lua_close(self.state)
            self.state = None
