@echo off
setlocal
rem Dedicated wheel-only experiment entry. This wrapper never selects the
rem rotation-inclusive baseline protocol.
call "%~dp0run_response_probe.bat" zoom_reversibility %*
