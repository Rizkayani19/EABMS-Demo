@echo off
echo Starting all EABMS Corporate instances...
start "" wscript.exe "%~dp0EABMS-NGL.vbs"
ping -n 3 127.0.0.1 >nul
start "" wscript.exe "%~dp0EABMS-EWF.vbs"
ping -n 3 127.0.0.1 >nul
start "" wscript.exe "%~dp0EABMS-CPF.vbs"
echo All EABMS services launched.
echo NGL: http://127.0.0.1:8020/
echo EWF: http://127.0.0.1:8021/
echo CPF: http://127.0.0.1:8022/
