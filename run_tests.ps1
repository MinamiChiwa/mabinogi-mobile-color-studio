[CmdletBinding()]
param(
    [ValidateSet('smoke', 'quick', 'release', 'research', 'full')]
    [string]$Suite = 'smoke',
    [string[]]$Modules,
    [switch]$List,
    [switch]$NoDesktop,
    [string]$Json
)
$ErrorActionPreference = 'Stop'
$testPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $testPython)) {
    throw 'Project Python is missing. Set up .venv before running tests.'
}
$testArgs = @((Join-Path $PSScriptRoot 'scripts\run_tests.py'), '--suite', $Suite)
if ($Modules) { $testArgs += @('--modules') + $Modules }
if ($List) { $testArgs += '--list' }
if ($NoDesktop) { $testArgs += '--no-desktop' }
if ($Json) { $testArgs += @('--json', $Json) }
& $testPython -X utf8 @testArgs
exit $LASTEXITCODE
