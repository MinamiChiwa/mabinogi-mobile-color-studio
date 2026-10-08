[CmdletBinding()]
param(
    [ValidateSet('production', 'diagnostics', 'legacy', 'fixtures', 'all')]
    [string]$Profile = 'production',
    [switch]$List
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Project Python is missing. Set up .venv before running tests.'
}
$testArgs = @((Join-Path $PSScriptRoot 'run_tests.py'), '--profile', $Profile)
if ($List) { $testArgs += '--list' }
& $python -X utf8 @testArgs
exit $LASTEXITCODE
