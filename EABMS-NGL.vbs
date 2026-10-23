Option Explicit
Dim WshShell, cmd, scriptDir
Set WshShell = CreateObject("WScript.Shell")
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "DEPLOYMENT\Windows\Start-EABMS.ps1"" -Account NGL"
WshShell.Run cmd, 0, False
Set WshShell = Nothing
