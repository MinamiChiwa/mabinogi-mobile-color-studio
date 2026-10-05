[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('baseline', 'rotation_compare', 'zoom_reversibility')]
    [string]$Protocol = 'baseline',
    [int]$ProbeCycles = 2,
    [string[]]$ProbeAnchors,
    [switch]$SkipPreflight
)

$ErrorActionPreference = 'Stop'
$validAnchors = @('center', 'offset', 'edge')
if ($ProbeAnchors) {
    # Accept both `-ProbeAnchors center,offset` and
    # `-ProbeAnchors center offset` in Windows PowerShell. Validate after
    # splitting comma-delimited values because ValidateSet on string[] treats
    # the comma form as one scalar argument.
    $ProbeAnchors = @($ProbeAnchors | ForEach-Object { $_ -split ',' } |
        ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $invalid = @($ProbeAnchors | Where-Object { $_ -notin $validAnchors })
    if ($invalid.Count -gt 0) {
        throw "Unknown probe anchor '$($invalid[0])'. Valid anchors: $($validAnchors -join ', ')"
    }
    if (@($ProbeAnchors | Select-Object -Unique).Count -ne $ProbeAnchors.Count) {
        throw 'Probe anchors must be unique.'
    }
}
$repo = $PSScriptRoot
$capture = Join-Path $repo 'work\studio\live_atlas_capture.py'
$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    $python = (Resolve-Path -LiteralPath $venvPython).Path
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python was not found.' }
    $python = $pythonCommand.Source
}
if (-not (Test-Path -LiteralPath $capture)) { throw "Capture entry was not found: $capture" }
$env:PYTHONPATH = (Join-Path $repo 'work\studio')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$out = Join-Path $repo (Join-Path 'outputs' ("response-probe-$stamp"))
$preflight = "$out-preflight"
Write-Host "Repo: $repo"
Write-Host "Python: $python"
Write-Host "Protocol: $Protocol"
Write-Host "Output: $out"
if (-not $SkipPreflight) {
    Write-Host 'Running read-only preflight...'
    & $python $capture 'preflight' $preflight
    if ($LASTEXITCODE -ne 0) { throw "Preflight failed: $preflight\preflight.json" }
}
Write-Host 'Keep the game in the foreground and enter the dye countdown manually. Press F9 to stop.'
if ($Protocol -eq 'zoom_reversibility') {
    Write-Host 'Wheel-only diagnostic; it does not confirm, apply, or cancel dye.'
} else {
    Write-Host 'Response diagnostic; it does not confirm, apply, or cancel dye.'
}
$invokeArgs = @($capture, 'acquire', $out, '--strategy', 'response', '--response-protocol', $Protocol, '--probe-cycles', [string]$ProbeCycles, '--mechanism-experiment')
if ($ProbeAnchors -and $ProbeAnchors.Count -gt 0) {
    $invokeArgs += '--probe-anchors'
    $invokeArgs += $ProbeAnchors
}
& $python @invokeArgs
$exitCode = $LASTEXITCODE
Write-Host "Experiment finished. Results: $out"
if ($exitCode -ne 0) { exit $exitCode }
