"""从本机安装准备外部运行依赖，不向项目目录写入客户端产物。"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from runtime_lua import RuntimeLua
from runtime_queries import TABLE_QUERY, DESCRIPTOR_QUERY


def external_path(path: Path) -> Path:
    """禁止在仓库目录内生成客户端代码或配置导出物。"""
    path = path.resolve()
    repo = Path(__file__).resolve().parent
    if path == repo or repo in path.parents:
        raise ValueError('运行依赖目录必须位于 Hoshimi 仓库之外')
    return path


def extract_lua(assets: Path, manifest: dict, output: Path) -> int:
    """从本机 scripts64 bundle 提取脚本，并限制输出文件名。"""
    import UnityPy

    rows = [r.split('|') for r in manifest['assetHashList'] if r.split('|')[0] == 'scripts64']
    if len(rows) != 1:
        raise ValueError('客户端清单没有唯一 scripts64 资源包，请检查版本')
    _, digest, size = rows[0]
    if not re.fullmatch(r'[a-f0-9]{32}', digest):
        raise ValueError('资源散列格式无效')
    candidates = [assets / digest[0] / digest[1] / (digest + '.ys'), assets / (digest + '.ys')]
    bundle = next((p for p in candidates if p.is_file()), None)
    if bundle is None:
        raise FileNotFoundError('本机缺少 scripts64 资源包，请通过官方启动器补齐资源后重试')
    raw = bundle.read_bytes()
    if len(raw) != int(size) or hashlib.md5(raw).hexdigest() != digest:
        raise ValueError('scripts64 大小或散列不符，请使用官方启动器修复资源')
    offset = raw.find(b'UnityFS')
    if offset < 0:
        raise ValueError('资源包不包含 UnityFS 标记')
    output.mkdir(parents=True)
    env = UnityPy.load(raw[offset:])
    count = 0
    entries = [(path, obj.read()) for path, obj in env.container.items() if obj.type.name == 'TextAsset']
    names = Counter(asset.m_Name.casefold() for _, asset in entries)
    for resource_path, asset in entries:
        name = asset.m_Name
        if not name.endswith(('.lua', '.lua.bytes')):
            name += '.lua'
        if Path(name).name != name or '/' in name or '\\' in name or ':' in name:
            raise ValueError('资源包含不安全的脚本文件名')
        data = asset.m_Script.encode('utf-8', errors='surrogateescape')
        # 非唯一名称保留原相对目录；配置和协议的唯一名称可直接由加载器读取。
        if names[asset.m_Name.casefold()] > 1:
            relative = Path(resource_path)
            if relative.is_absolute() or '..' in relative.parts or ':' in resource_path:
                raise ValueError('资源路径不安全')
            target = output / 'modules' / relative.parent / name
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target = output / name
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f'资源存在重名且内容不同的脚本：{name}')
        target.write_bytes(data)
        count += 1
    if not (output / 'HeroCfg.lua').is_file() or not (output / 'p10_pb.lua').is_file():
        raise ValueError('提取结果缺少基础配置或登录协议')
    return count


def protocol_map(descriptors: list[dict]) -> dict:
    """按消息及模块名称建立协议索引，补齐可空字段。"""
    result = {}
    for row in sorted(descriptors, key=lambda r: (r['module'], r['name'], r['descriptor_key'])):
        fields = sorted(row['fields'], key=lambda f: f['tag'])
        for field in fields:
            for key in ('sub_type', 'sub_full_name', 'default'):
                field.setdefault(key, None)
        match = re.fullmatch(r'(cs|sc)_(\d+)', row['name'])
        entry = {k: row[k] for k in ('name', 'module', 'full_name')}
        entry.update(protocol_id=int(match[2]) if match else None, direction=match[1] if match else None,
                     field_count=len(fields), fields=fields,
                     fields_by_tag={str(f['tag']): f for f in fields},
                     fields_by_name={f['name']: f for f in fields})
        if match:
            result[row['name']] = entry
        else:
            result.setdefault(row['name'], entry)
            result[row['module'] + '.' + row['name']] = entry
    for name in ('cs_10038', 'sc_10039', 'cs_10042', 'sc_10043', 'cs_10200', 'sc_10201'):
        if name not in result:
            raise ValueError(f'客户端缺少必要协议：{name}')
    return result


def prepare(client: Path, runtime: Path) -> None:
    """在仓库外准备完整依赖，成功后才替换旧运行目录并保留备份。"""
    runtime = external_path(runtime)
    client = client.resolve()
    if client == runtime or runtime in client.parents or client in runtime.parents:
        raise ValueError('运行依赖目录和客户端安装目录不能相互包含')
    assets = client / 'AetherGazer_Data' / 'StreamingAssets' / 'Windows'
    dll = client / 'AetherGazer_Data' / 'Plugins' / 'x86_64' / 'tolua.dll'
    if not dll.is_file() or sys.maxsize <= 2**32:
        raise ValueError('需要本机完整 PC 客户端及 64 位 Python')
    manifest_raw = (assets / 'AssetHash_Info.bytes').read_bytes()
    manifest = json.loads(manifest_raw)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=runtime.name + '-prepare-', dir=runtime.parent))
    count = extract_lua(assets, manifest, staging / 'lua')
    print(f'已从本机客户端准备 {count} 个脚本，正在读取配置与协议。')
    lua = RuntimeLua(dll, staging / 'lua')
    try:
        tables = lua.read(TABLE_QUERY)
        modules = sorted(p.stem for p in (staging / 'lua').glob('p*_pb.lua') if re.fullmatch(r'p\d+_pb', p.stem))
        names = '{' + ','.join('"' + name + '"' for name in modules) + '}'
        query = DESCRIPTOR_QUERY.replace('MODULE_NAMES', names)
        protocols = protocol_map(lua.read(query))
    finally:
        lua.close()
    for name, value in [('tables.json', tables), ('protocol_map.json', protocols)]:
        (staging / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    metadata = {'schema_version': 1, 'client_dir': str(client), 'app_version': manifest['appVersion'],
                'build_code': manifest['buildCode'], 'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest()}
    (staging / 'runtime.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    if runtime.exists():
        backup = runtime.with_name(runtime.name + '-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        runtime.rename(backup)
        print(f'旧依赖已备份到：{backup}')
    staging.rename(runtime)
    print(f'准备完成：{runtime}')
    print(f'角色 {len(tables["HERO_DEFINITIONS"])}、货币 {len(tables["CURRENCY_DEFINITIONS"])}、补给 {len(tables["SUPPLY_DEFINITIONS"])}、协议索引 {len(protocols)}。')


def main() -> None:
    """读取参数或环境变量，不修改客户端安装与账号存档。"""
    parser = argparse.ArgumentParser(description='准备本机外部运行依赖；请勿分享生成结果')
    parser.add_argument('--client-dir', default=os.getenv('AGL_CLIENT_DIR'))
    parser.add_argument('--runtime-dir', default=os.getenv('HOSHIMI_RUNTIME_DIR', str(Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'Hoshimi' / 'runtime')))
    args = parser.parse_args()
    if not args.client_dir:
        parser.error('请设置 AGL_CLIENT_DIR 或传入 --client-dir')
    try:
        prepare(Path(args.client_dir), Path(args.runtime_dir))
    except Exception as error:
        parser.exit(1, f'准备失败：{error}\n失败的中间结果仍在仓库外，可检查后手动清理。\n')


if __name__ == '__main__':
    main()
