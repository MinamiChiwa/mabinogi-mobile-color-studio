$ErrorActionPreference = 'Stop'
$checkExe = Join-Path $PSScriptRoot 'ColorStudio.exe'
if (-not (Test-Path -LiteralPath $checkExe -PathType Leaf)) {
    throw 'Run this script from the folder containing ColorStudio.exe.'
}
$checkOutput = Join-Path $PSScriptRoot ('data/window-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $checkOutput -Force | Out-Null
$checkArguments = '--native-preflight --output-dir "' + $checkOutput + '"'
$checkProcess = Start-Process -FilePath $checkExe -ArgumentList $checkArguments -WindowStyle Hidden -PassThru
$checkProcess.WaitForExit()
Write-Host ('Read-only diagnostic saved to: ' + $checkOutput)
Write-Host 'This check does not enter dyeing or send game input.'
if ($checkProcess.ExitCode -ne 0) {
    Write-Host 'The diagnostic found an unsupported condition. See native-preflight.json and native-preparation.json.'
}
exit $checkProcess.ExitCode
