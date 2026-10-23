@echo off
echo Stopping EABMS instances (ports 8020, 8021, 8022)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-NetTCPConnection -LocalPort 8020,8021,8022 -ErrorAction SilentlyContinue | " ^
  "Select-Object -ExpandProperty OwningProcess -Unique | " ^
  "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; Write-Host ('Stopped PID ' + $_) }"
echo Done.
