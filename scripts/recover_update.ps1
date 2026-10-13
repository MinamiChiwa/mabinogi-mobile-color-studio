[CmdletBinding()]
param([string]$Installation)
$ErrorActionPreference = 'Stop'
if (-not $Installation) {
    Add-Type -AssemblyName System.Windows.Forms
    $picker = New-Object System.Windows.Forms.FolderBrowserDialog
    $picker.Description = '选择 ColorStudio.exe 所在目录。请先正常关闭染色工具。'
    $picker.ShowNewFolderButton = $false
    if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
    $Installation = $picker.SelectedPath
}
$root = (Get-Item -LiteralPath $Installation).FullName
$marker = Join-Path $root '.colorstudio-pending.json'
if (-not (Test-Path -LiteralPath $marker)) {
    throw '没有待续装的更新记录。请先在旧工具内下载更新并点击安装；若安装超时，再关闭工具后运行本修复包。'
}
$pending = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
$tx = (Get-Item -LiteralPath $pending.transaction).FullName
$record = Get-Content -LiteralPath (Join-Path $tx 'transaction.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ([IO.Path]::GetFullPath($record.root).TrimEnd('\') -ne $root.TrimEnd('\')) { throw '更新记录与所选工具目录不符。' }
$state = Get-Content -LiteralPath (Join-Path $tx 'state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($state.status -ne 'staged') { throw '本修复包仅续装尚未替换文件的更新。请保留记录；其他状态需要单独恢复。' }
$helper = Join-Path $PSScriptRoot 'ColorStudioUpdater.exe'
# The independent helper verifies production signatures and all staged file
# hashes, rejects other running app instances, and retains normal rollback.
$process = Start-Process -FilePath $helper -ArgumentList @('--transaction', ('"' + $tx + '"')) -WindowStyle Hidden -PassThru
$process.WaitForExit()
$process.Refresh()
if ($process.ExitCode -ne 0) { throw '更新未完成。请保留更新记录和原目录。' }
Write-Output '更新已完成，工具会自动重新打开。颜色、方案和历史已保留。'
