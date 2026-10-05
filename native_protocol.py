"""读取客户端 native 战斗 protobuf 的基本字段。"""


def varint(value: int) -> bytes:
    """编码无符号整数，64 位数不经过 Lua 浮点数。"""
    value &= 0xffffffffffffffff
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """读取完整 varint，截断或超长数据直接拒绝。"""
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('原生 protobuf 数据被截断')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('原生 protobuf varint 过长')


def fields(data: bytes) -> dict:
    """读取整数和嵌套字节字段，保留 repeated 字段顺序。"""
    result = {}
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire in (1, 2, 5):
            size = 8 if wire == 1 else 4
            if wire == 2:
                size, offset = read_varint(data, offset)
            if offset + size > len(data):
                raise ValueError('原生 protobuf 字段被截断')
            value = data[offset:offset+size]
            offset += size
        else:
            raise ValueError('未知的原生 protobuf 编码类型')
        result.setdefault(number, []).append(value)
    return result


def integer(number: int, value: int) -> bytes:
    """编码整数 protobuf 字段。"""
    return varint(number << 3) + varint(value)


def message(number: int, value: bytes) -> bytes:
    """编码嵌套 protobuf 字段。"""
    return varint((number << 3) | 2) + varint(len(value)) + value


def repeated_integers(values: list) -> list[int]:
    """兼容 protobuf repeated 整数的 packed 与普通编码。"""
    result = []
    for value in values:
        if isinstance(value, int):
            result.append(value)
        else:
            offset = 0
            while offset < len(value):
                item, offset = read_varint(value, offset)
                result.append(item)
    return result


def battle_report(data: bytes) -> dict:
    """保留结算统计、物品计数和每个角色的真实剩余生命。"""
    decoded = fields(data)
    result = {str(k): v[0] for k, v in decoded.items() if k <= 11 and k != 10 and isinstance(v[0], int)}
    result['characters'] = [{str(k): v[0] for k, v in fields(c).items()} for c in decoded.get(10, [])]
    for key in range(12, 19):
        result[str(key)] = repeated_integers(decoded.get(key, []))
    return result
