#Requires -Version 7.0
[CmdletBinding()]
param([string]$Restore)

$ErrorActionPreference = 'Stop'
$repoDir = Split-Path $PSScriptRoot -Parent
$prefsPath = 'HKCU:\Software\yongshi\AetherGazer'
$settingKey = 'userSetting_h136201570'
$keyboardKey = 'KeyboardType_h1853033200'

function Get-ClientSetting {
    # 读取 Unity PlayerPrefs 的 UTF-8 JSON，保留其余用户设置。
    $raw = (Get-Item -LiteralPath $prefsPath).GetValue($settingKey)
    if ($raw -is [byte[]]) { $raw = [Text.Encoding]::UTF8.GetString($raw).TrimEnd([char]0) }
    if ([string]::IsNullOrEmpty($raw)) { return @{} }
    return ConvertFrom-Json -InputObject $raw -AsHashtable
}

function Set-ClientSetting {
    # 按 Unity 的二进制字符串格式保存设置。
    param([hashtable]$Settings)
    $json = ConvertTo-Json -InputObject $Settings -Depth 30 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json + [char]0)
    New-ItemProperty -LiteralPath $prefsPath -Name $settingKey -PropertyType Binary -Value $bytes -Force | Out-Null
}

if (Get-Process -Name AetherGazer -ErrorAction SilentlyContinue) {
    throw '请先退出游戏再运行，避免客户端退出时覆盖修复后的设置。'
}
if (!(Test-Path -LiteralPath $prefsPath)) { throw '未找到客户端设置，请先启动过一次游戏。' }
$settings = Get-ClientSetting
$layoutFields = @('battle_ui_cur_type', 'battle_ui_cur_alpha_value')
if ($Restore) {
    $backup = Get-Content -LiteralPath $Restore -Raw | ConvertFrom-Json -AsHashtable
    foreach ($name in $layoutFields) {
        if ($backup.layout.ContainsKey($name)) { $settings[$name] = $backup.layout[$name] }
        else { $settings.Remove($name) }
    }
    Set-ClientSetting $settings
    if ($null -eq $backup.keyboard) { Remove-ItemProperty -LiteralPath $prefsPath -Name $keyboardKey -ErrorAction SilentlyContinue }
    else { New-ItemProperty -LiteralPath $prefsPath -Name $keyboardKey -PropertyType DWord -Value $backup.keyboard -Force | Out-Null }
    Write-Output '已恢复备份中的战斗布局和控制模式。'
    return
}
$layout = @{}
foreach ($name in $layoutFields) { if ($settings.ContainsKey($name)) { $layout[$name] = $settings[$name] } }
$backupDirectory = Join-Path $repoDir 'data/client-settings'
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$backupFile = Join-Path $backupDirectory ('battle-controls-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
@{layout=$layout; keyboard=(Get-Item -LiteralPath $prefsPath).GetValue($keyboardKey)} |
    ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $backupFile -Encoding utf8
# 空布局让 PC 适配器使用内置布局；删除此键会再次加载异常的初始布局。
$settings['battle_ui_cur_type'] = ''
$settings['battle_ui_cur_alpha_value'] = 1
Set-ClientSetting $settings
New-ItemProperty -LiteralPath $prefsPath -Name $keyboardKey -PropertyType DWord -Value 5 -Force | Out-Null
Write-Output "已恢复 PC 战斗布局并启用键鼠模式。备份：$backupFile"
