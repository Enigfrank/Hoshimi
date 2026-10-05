#requires -Version 7.0
<#
.SYNOPSIS
切换深空之眼官服与 AGL 本地服，分别保存 SDK 登录缓存。
.EXAMPLE
pwsh -File ./scripts/switch-client.ps1 -Mode Local -ClientDir 'E:\AetherGazerLauncher\AetherGazer'
.EXAMPLE
pwsh -File ./scripts/switch-client.ps1 -Mode Official -ClientDir 'E:\AetherGazerLauncher\AetherGazer'
#>
[CmdletBinding()]
param(
    [ValidateSet('Local', 'Official', 'Status')]
    [string]$Mode,
    [string]$ClientDir = $env:AGL_CLIENT_DIR,
    [ValidateRange(1, 65535)]
    [int]$LocalPort = 8080,
    [string]$OfficialConfigPath,
    [string]$StateDir = ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../data/client-switch'))),
    [string]$HostsPath = (Join-Path $env:SystemRoot 'System32/drivers/etc/hosts'),
    [string]$PrefsDir = (Join-Path $env:USERPROFILE 'AppData/LocalLow/yongshi/AetherGazer')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sdk-config.ps1')
$domains = @('open.ys4fun.com', 'webstatic.ys4fun.com', 'prod-api-activity.ys4fun.com')
$prefsNames = @('ys_mix_prefs.json', 'ys_prefs.json')
$modeLabels = @{ Local = '本地服'; Official = '官服'; Status = '查看状态' }

function Get-ClientMode {
    # 从入口 URL 判断当前环境，不读取登录令牌。
    param([string]$ConfigPath)
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $uri = [uri]$config.url
    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -notin @('http', 'https')) {
        throw "入口配置不是有效 HTTP URL：$ConfigPath"
    }
    if ($uri.IsLoopback) { return 'Local' }
    return 'Official'
}

function Get-SwitchHosts {
    # 只移除指定域名的回环映射，同一行的其他域名和其他 hosts 行保持有效。
    param([string]$Content, [string]$TargetMode)
    $lines = foreach ($line in ($Content -split '\r?\n')) {
        $parts = $line -split '#', 2
        $tokens = @($parts[0].Trim() -split '\s+' | Where-Object { $_ })
        if ($tokens.Count -lt 2) { $line; continue }
        $matched = @($tokens[1..($tokens.Count - 1)] | Where-Object { $_ -in $domains })
        if (-not $matched.Count) { $line; continue }
        if ($tokens[0] -notin @('127.0.0.1', '::1')) {
            if ($TargetMode -eq 'Local') { throw "hosts 存在非回环映射，请先检查：$line" }
            $line; continue
        }
        $remaining = @($tokens[1..($tokens.Count - 1)] | Where-Object { $_ -notin $domains })
        if ($remaining.Count) {
            $rebuilt = $tokens[0] + ' ' + ($remaining -join ' ')
            if ($parts.Count -eq 2) { $rebuilt += ' #' + $parts[1] }
            $rebuilt
        }
    }
    $result = ($lines -join "`r`n").TrimEnd("`r", "`n") + "`r`n"
    return $result
}

function Save-CacheProfile {
    # 保存当前模式的两份 SDK 缓存；缺失的文件也作为该模式的状态记录。
    param([string]$ProfileDir)
    $null = New-Item -ItemType Directory -Path $ProfileDir -Force
    foreach ($name in $prefsNames) {
        $source = Join-Path $PrefsDir $name
        $target = Join-Path $ProfileDir $name
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $target -Force }
        elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
    }
}

function Restore-CacheProfile {
    # 恢复目标模式的缓存；首次切换无缓存时退出自动登录，交由客户端重新登录。
    param([string]$ProfileDir)
    $null = New-Item -ItemType Directory -Path $PrefsDir -Force
    foreach ($name in $prefsNames) {
        $source = Join-Path $ProfileDir $name
        $target = Join-Path $PrefsDir $name
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $target -Force }
        elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
    }
}

if (-not $ClientDir) {
    throw '请通过 -ClientDir 或 AGL_CLIENT_DIR 指定包含 AetherGazer.exe 的游戏目录。'
}
$ClientDir = (Resolve-Path -LiteralPath $ClientDir).Path
$urlPath = Join-Path $ClientDir 'AetherGazer_Data/StreamingAssets/url.txt'
$resourcesPath = Join-Path $ClientDir 'AetherGazer_Data/resources.assets'
if (-not (Test-Path -LiteralPath $urlPath)) { throw "找不到客户端入口文件：$urlPath" }
$currentMode = Get-ClientMode $urlPath
$statePath = Join-Path $StateDir 'state.json'
$officialPath = Join-Path $StateDir 'official-url.bak'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state.clientDir -ne $ClientDir -or $state.prefsDir -ne [IO.Path]::GetFullPath($PrefsDir)) {
        throw '此备份目录属于其他客户端或缓存目录，请用 -StateDir 指定不同目录。'
    }
}
if (-not $Mode) {
    Write-Host "当前入口：$($modeLabels[$currentMode])"
    $choice = Read-Host '1 = 本地服，2 = 官服，3 = 查看状态'
    $Mode = switch ($choice) { '1' { 'Local' } '2' { 'Official' } '3' { 'Status' } default { throw '请选择 1、2 或 3。' } }
}
if ($Mode -eq 'Status') {
    Write-Host "客户端：$ClientDir"
    Write-Host "入口环境：$($modeLabels[$currentMode])"
    Write-Host "备份目录：$([IO.Path]::GetFullPath($StateDir))"
    Write-Host "官服入口备份：$(if (Test-Path -LiteralPath $officialPath) { '已保存' } else { '未保存' })"
    Get-Content -LiteralPath $HostsPath | Where-Object { $_ -match 'ys4fun\.com' } | Write-Host
    exit 0
}
if (Get-Process -Name AetherGazer -ErrorAction SilentlyContinue | Where-Object {
    -not $_.Path -or $_.Path -eq (Join-Path $ClientDir 'AetherGazer.exe')
}) {
    throw '请先退出游戏客户端，再切换环境。脚本不会强制结束游戏。'
}
if (-not (Test-Path -LiteralPath $resourcesPath)) { throw "找不到 SDK 资源文件：$resourcesPath" }
$hostsBefore = [IO.File]::ReadAllText($HostsPath)
$hostsAfter = Get-SwitchHosts $hostsBefore $Mode
$systemHosts = Join-Path $env:SystemRoot 'System32/drivers/etc/hosts'
$useSystemHosts = [IO.Path]::GetFullPath($HostsPath) -eq [IO.Path]::GetFullPath($systemHosts)
$proxyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$disableLocalProxy = $false
if ($useSystemHosts) {
    if ($hostsAfter -ne $hostsBefore) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw '修改 hosts 需要管理员权限。请以管理员身份打开 PowerShell 7 后重试。'
        }
    }
    $proxy = Get-ItemProperty -LiteralPath $proxyPath
    if ($proxy.ProxyEnable -eq 1) {
        $serverProperty = $proxy.PSObject.Properties['ProxyServer']
        $proxyServer = if ($serverProperty) { [string]$serverProperty.Value } else { '' }
        $localProxy = $proxyServer -in @("127.0.0.1:$LocalPort", "localhost:$LocalPort")
        if ($localProxy) { $disableLocalProxy = $true }
        elseif ($Mode -eq 'Local' -and -not $localProxy) {
            throw '当前系统代理已启用，可能覆盖 hosts 路由。请先关闭代理再切换；脚本不会更改其他代理配置。'
        }
    }
}
# 优先使用已有官服备份；当前已是本地服时，不能把本地 URL 当作官服备份。
$officialSource = $null
if (Test-Path -LiteralPath $officialPath) { $officialSource = $officialPath }
elseif ($OfficialConfigPath) { $officialSource = $OfficialConfigPath }
elseif ($currentMode -eq 'Official') { $officialSource = $urlPath }
if (-not $officialSource -or (Get-ClientMode $officialSource) -ne 'Official') {
    throw '缺少有效官服入口备份。请用 -OfficialConfigPath 指向原始 url.txt。'
}
$null = New-Item -ItemType Directory -Path $StateDir -Force
if (-not (Test-Path -LiteralPath $officialPath)) {
    Copy-Item -LiteralPath $officialSource -Destination $officialPath
}
# 保存失败回滚所需的原始字节，备份目录也保留首次使用时的配置。
if (-not (Test-Path -LiteralPath (Join-Path $StateDir 'initial-hosts.bak'))) {
    Copy-Item -LiteralPath $HostsPath -Destination (Join-Path $StateDir 'initial-hosts.bak')
}
$snapshot = @{}
foreach ($path in @($urlPath, $resourcesPath, $HostsPath) + @($prefsNames | ForEach-Object { Join-Path $PrefsDir $_ })) {
    if (Test-Path -LiteralPath $path) { $snapshot[$path] = [IO.File]::ReadAllBytes($path) }
    else { $snapshot[$path] = $null }
}
Save-CacheProfile (Join-Path $StateDir $currentMode)
try {
    Set-SdkEndpoints $resourcesPath $Mode $LocalPort $StateDir
    if ($Mode -eq 'Local') {
        $config = Get-Content -LiteralPath $officialPath -Raw | ConvertFrom-Json
        $config.url = "http://127.0.0.1:$LocalPort/skzy-activity/gateway/get"
        [IO.File]::WriteAllText($urlPath, ($config | ConvertTo-Json -Compress))
    } else { Copy-Item -LiteralPath $officialPath -Destination $urlPath -Force }
    if ($hostsAfter -ne $hostsBefore) { [IO.File]::WriteAllText($HostsPath, $hostsAfter) }
    if ($Mode -ne $currentMode) { Restore-CacheProfile (Join-Path $StateDir $Mode) }
    if ($disableLocalProxy) { Set-ItemProperty -LiteralPath $proxyPath -Name ProxyEnable -Value 0 }
    @{ clientDir = $ClientDir; prefsDir = [IO.Path]::GetFullPath($PrefsDir); mode = $Mode } |
        ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
} catch {
    $switchError = $_
    foreach ($path in $snapshot.Keys) {
        try {
            if ($null -ne $snapshot[$path]) {
                $unchanged = (Test-Path -LiteralPath $path) -and
                    [Convert]::ToBase64String([IO.File]::ReadAllBytes($path)) -ceq [Convert]::ToBase64String($snapshot[$path])
                if (-not $unchanged) { [IO.File]::WriteAllBytes($path, $snapshot[$path]) }
            } elseif (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
        } catch { Write-Warning "无法回滚 $path，请使用备份恢复：$($_.Exception.Message)" }
    }
    if ($disableLocalProxy) { Set-ItemProperty -LiteralPath $proxyPath -Name ProxyEnable -Value 1 }
    throw $switchError
}
if ($useSystemHosts) {
    try { Clear-DnsClientCache } catch { Write-Warning 'DNS 缓存刷新失败，请关闭客户端后执行 ipconfig /flushdns。' }
}
Write-Host "已切换：$($modeLabels[$Mode])。配置和两套 SDK 缓存保存在 $([IO.Path]::GetFullPath($StateDir))"
if ($Mode -eq 'Local') { Write-Host 'SDK 使用本地 HTTP；资源使用官方 HTTPS CDN。无需导入本地证书。请先启动 python server.py。' }
else { Write-Host '请通过官方启动器打开游戏；首次切回官服可能需要重新登录。' }
