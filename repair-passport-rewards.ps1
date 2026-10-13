#Requires -Version 7.0
<#
.SYNOPSIS
修复通行证购买写入的 passport_rewards 类型错误。
.DESCRIPTION
检测数字用户存档中的 passport_rewards。若 id/is_pay 不是协议要求的数字，
先备份原文件，再移除损坏字段；服务端会按未领取通行证奖励处理。
.EXAMPLE
pwsh -File ./scripts/repair-passport-rewards.ps1
.EXAMPLE
pwsh -File ./scripts/repair-passport-rewards.ps1 -UserDir 'D:\Hoshimi\app\data\users'
#>
[CmdletBinding()]
param(
    [string]$UserDir = (Join-Path $PSScriptRoot '..\data\users'),
    [string]$BackupDir = (Join-Path $PSScriptRoot '..\data\users\backup')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-UInt32Value {
    param([object]$Value)

    if ($null -eq $Value -or $Value -is [bool]) { return $false }
    try {
        $number = [Convert]::ToUInt64($Value)
        return $number -le [uint32]::MaxValue
    } catch {
        return $false
    }
}

function Test-MalformedPassportRewards {
    param([object]$User)

    $property = $User.PSObject.Properties['passport_rewards']
    if ($null -eq $property) { return $false }

    $rewards = $property.Value
    if ($null -eq $rewards) { return $true }
    if ($rewards -isnot [array]) { return $true }

    foreach ($reward in $rewards) {
        if ($null -eq $reward) { return $true }
        $id = $reward.PSObject.Properties['id']
        $isPay = $reward.PSObject.Properties['is_pay']
        if ($null -eq $id -or $null -eq $isPay) { return $true }
        if (-not (Test-UInt32Value $id.Value)) { return $true }
        if (-not (Test-UInt32Value $isPay.Value)) { return $true }
    }

    return $false
}

if (Get-Process -Name hoshimi -ErrorAction SilentlyContinue) {
    throw '请先停止 Hoshimi 服务端，再修复存档。'
}

$UserDir = (Resolve-Path -LiteralPath $UserDir).Path
$null = New-Item -ItemType Directory -Path $BackupDir -Force
$files = Get-ChildItem -LiteralPath $UserDir -File -Filter '*.json' |
    Where-Object { $_.BaseName -match '^\d+$' }
if (-not $files) { throw "未找到数字用户存档：$UserDir" }

$repaired = 0
foreach ($file in $files) {
    $user = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not (Test-MalformedPassportRewards $user)) { continue }

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $backupPath = Join-Path $BackupDir ($file.BaseName + '.passport-rewards-' + $timestamp + '.json')
    Copy-Item -LiteralPath $file.FullName -Destination $backupPath

    $user.PSObject.Properties.Remove('passport_rewards')
    $json = $user | ConvertTo-Json -Depth 100 -Compress
    $tempPath = Join-Path $file.DirectoryName ($file.Name + '.hoshimi-write-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($tempPath, $json, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $tempPath -Destination $file.FullName -Force
    } finally {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }

    $repaired++
    Write-Output "已修复：$($file.FullName)"
    Write-Output "备份：$backupPath"
}

if ($repaired -eq 0) {
    Write-Output '未发现 passport_rewards 类型错误。'
} else {
    Write-Output "修复完成，共处理 $repaired 个存档。"
}
