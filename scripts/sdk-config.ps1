#requires -Version 7.0
# SDK 配置保持原长度写回 Unity 资源文件，不修改可执行代码。

function Get-SdkBlock {
    # 根据 TextAsset 名称定位唯一配置块并解密，拒绝不匹配的资源格式。
    param([byte[]]$Bytes, [string]$Name)
    $binaryText = [Text.Encoding]::Latin1.GetString($Bytes)
    $nameOffset = $binaryText.IndexOf($Name, [StringComparison]::Ordinal)
    if ($nameOffset -lt 4 -or $binaryText.IndexOf($Name, $nameOffset + $Name.Length, [StringComparison]::Ordinal) -ge 0) {
        throw "无法定位唯一 SDK 配置：$Name"
    }
    if ([BitConverter]::ToInt32($Bytes, $nameOffset - 4) -ne $Name.Length) { throw "SDK 配置名称格式错误：$Name" }
    $lengthOffset = $nameOffset + [int]([Math]::Ceiling($Name.Length / 4.0) * 4)
    $length = [BitConverter]::ToInt32($Bytes, $lengthOffset)
    $offset = $lengthOffset + 4
    if ($length -le 0 -or $length -gt 65536 -or $offset + $length -gt $Bytes.Length) { throw "SDK 配置长度错误：$Name" }
    $encoded = [Text.Encoding]::ASCII.GetString($Bytes, $offset, $length)
    $ciphertext = [Convert]::FromBase64String($encoded)
    $aes = [Security.Cryptography.Aes]::Create()
    try {
        $aes.Key = [Text.Encoding]::ASCII.GetBytes('ys4fun' + ('0' * 26))
        $aes.Mode = [Security.Cryptography.CipherMode]::ECB
        $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
        $decryptor = $aes.CreateDecryptor()
        try { $plain = $decryptor.TransformFinalBlock($ciphertext, 0, $ciphertext.Length) }
        finally { $decryptor.Dispose() }
        $config = [Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json -AsHashtable
    } finally { $aes.Dispose() }
    return @{ Offset = $offset; Length = $length; Encoded = $encoded; CipherLength = $ciphertext.Length; Config = $config }
}

function Set-SdkEndpoints {
    # 保存官服配置并切换 prod 地址；切回官服时恢复原配置，保留资源文件的其他字节。
    param([string]$ResourcesPath, [string]$TargetMode, [int]$Port, [string]$BackupDir)
    $bytes = [IO.File]::ReadAllBytes($ResourcesPath)
    foreach ($entry in @(
        @{ Name = 'ysmix_config'; Key = 'YS_MIX_SDK_URL'; Path = 'mix-sdk-api/' },
        @{ Name = 'ys_config'; Key = 'YS4FUN_SDK_URL'; Path = 'sdk-api/' }
    )) {
        $block = Get-SdkBlock $bytes $entry.Name
        $config = $block.Config
        $currentUrl = [uri]$config.prod[$entry.Key]
        $backupPath = Join-Path $BackupDir ($entry.Name + '.sdk.bak')
        if (Test-Path -LiteralPath $backupPath) {
            $encoded = [IO.File]::ReadAllText($backupPath)
            # 两个方向都先检查版本，避免写入本地配置后无法恢复官服。
            $check = [byte[]]$bytes.Clone()
            $backupBytes = [Text.Encoding]::ASCII.GetBytes($encoded)
            if ($backupBytes.Length -ne $block.Length) { throw 'SDK 备份版本不匹配，请用启动器修复客户端后重新备份。' }
            [Array]::Copy($backupBytes, 0, $check, $block.Offset, $backupBytes.Length)
            $original = (Get-SdkBlock $check $entry.Name).Config
            $original.prod[$entry.Key] = $config.prod[$entry.Key]
            if (($original | ConvertTo-Json -Compress -Depth 30) -cne ($config | ConvertTo-Json -Compress -Depth 30)) {
                throw 'SDK 配置已更新，请用启动器修复客户端并为新版本选择新的 -StateDir。'
            }
        }
        if ($TargetMode -eq 'Local') {
            if (-not (Test-Path -LiteralPath $backupPath)) {
                if ($currentUrl.Scheme -ne 'https' -or $currentUrl.IsLoopback) { throw "缺少 SDK 官服备份：$($entry.Name)" }
                [IO.File]::WriteAllText($backupPath, $block.Encoded)
            }
            $config.prod[$entry.Key] = "http://127.0.0.1:$Port/$($entry.Path)"
            $plain = [Text.Encoding]::UTF8.GetBytes(($config | ConvertTo-Json -Compress -Depth 30))
            $targetLength = $block.CipherLength - 16
            if ($plain.Length -gt $targetLength) { throw "SDK 新配置超过原空间：$($entry.Name)" }
            $padded = [byte[]]::new($targetLength)
            [Array]::Fill[byte]($padded, 32)
            [Array]::Copy($plain, $padded, $plain.Length)
            $aes = [Security.Cryptography.Aes]::Create()
            try {
                $aes.Key = [Text.Encoding]::ASCII.GetBytes('ys4fun' + ('0' * 26))
                $aes.Mode = [Security.Cryptography.CipherMode]::ECB
                $encryptor = $aes.CreateEncryptor()
                try { $encoded = [Convert]::ToBase64String($encryptor.TransformFinalBlock($padded, 0, $padded.Length)) }
                finally { $encryptor.Dispose() }
            } finally { $aes.Dispose() }
        } elseif (Test-Path -LiteralPath $backupPath) {
            # 前面的版本检查已读取原始编码，直接恢复。
        } elseif ($currentUrl.Scheme -eq 'https' -and -not $currentUrl.IsLoopback) { continue }
        else { throw "缺少 SDK 官服备份：$($entry.Name)" }
        $updated = [Text.Encoding]::ASCII.GetBytes($encoded)
        if ($updated.Length -ne $block.Length) { throw "SDK 编码长度变化：$($entry.Name)" }
        [Array]::Copy($updated, 0, $bytes, $block.Offset, $updated.Length)
    }
    [IO.File]::WriteAllBytes($ResourcesPath, $bytes)
}
