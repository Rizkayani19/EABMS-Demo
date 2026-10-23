<#
.SYNOPSIS
    Start-EABMS.ps1 — Launch an EABMS account server (NGL / EWF / CPF)
.PARAMETER Account
    Account code to launch: NGL (port 8020), EWF (port 8021), CPF (port 8022)
.PARAMETER AppMode
    If specified, opens Microsoft Edge in App Mode after server starts.
#>
param(
    [string]$Account = 'NGL',
    [switch]$AppMode
)

$EABMS_ROOT   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BACKEND_DIR  = Join-Path $EABMS_ROOT '02_Backend'

$localVenv = Join-Path $BACKEND_DIR 'venv\Scripts\python.exe'
if (Test-Path $localVenv) {
    $PYTHON_EXE = $localVenv
} elseif (Test-Path 'd:\ABMS\02_Backend\venv\Scripts\python.exe') {
    $PYTHON_EXE = 'd:\ABMS\02_Backend\venv\Scripts\python.exe'
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    $PYTHON_EXE = if ($cmd) { $cmd.Source } else { 'python.exe' }
}

$PORT_MAP = @{ NGL = 8020; EWF = 8021; CPF = 8022 }
$NAME_MAP = @{ NGL = 'NexGen Holdings Ltd.'; EWF = 'Employee Welfare Fund'; CPF = 'Corporate Provident Fund' }

if (-not $PORT_MAP.ContainsKey($Account)) {
    Write-Host "Unknown account '$Account'. Use NGL, EWF, or CPF." -ForegroundColor Red
    exit 1
}

$Port = $PORT_MAP[$Account]
$Name = $NAME_MAP[$Account]

Write-Host "Enterprise Accounts & Business Management System (EABMS)" -ForegroundColor Cyan
Write-Host "  Account : $Name ($Account)" -ForegroundColor White
Write-Host "  Port    : $Port" -ForegroundColor White
Write-Host "  URL     : http://127.0.0.1:$Port/" -ForegroundColor White

# ── Test if already running ──────────────────────────────────────────────────
function Test-PortOpen([int]$p) {
    try {
        $tc = New-Object System.Net.Sockets.TcpClient
        $tc.Connect('127.0.0.1', $p)
        $tc.Close()
        return $true
    } catch { return $false }
}

if (Test-PortOpen $Port) {
    Write-Host "  Server already running on port $Port." -ForegroundColor Green
} else {
    # ── Start Waitress server ─────────────────────────────────────────────────
    function Start-DetachedProcess([string]$exePath, [string[]]$arguments, [string]$workDir) {
        try {
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName         = $exePath
            $psi.Arguments        = $arguments -join ' '
            $psi.WorkingDirectory = $workDir
            $psi.UseShellExecute  = $false
            $psi.CreateNoWindow   = $true
            $psi.WindowStyle      = [System.Diagnostics.ProcessWindowStyle]::Hidden
            $psi.EnvironmentVariables['ABMS_FUND'] = $Account
            $proc = [System.Diagnostics.Process]::Start($psi)
            return $proc.Id
        } catch {
            $p = Start-Process -FilePath $exePath -ArgumentList $arguments -WorkingDirectory $workDir -WindowStyle Hidden -PassThru
            return $p.Id
        }
    }

    $env:ABMS_FUND = $Account
    $waitressArgs = @('-m', 'waitress', "--listen=127.0.0.1:$Port", 'abms_config.wsgi:application')
    $pid1 = Start-DetachedProcess $PYTHON_EXE $waitressArgs $BACKEND_DIR
    Write-Host "  Started waitress (PID $pid1) on port $Port..." -ForegroundColor Yellow

    # Wait for server to be ready (up to 30s)
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep 1
        if (Test-PortOpen $Port) { $ready = $true; break }
    }
    if ($ready) {
        Write-Host "  Server ready at http://127.0.0.1:$Port/" -ForegroundColor Green
    } else {
        Write-Host "  Warning: server may not be ready yet." -ForegroundColor Yellow
    }
}

# ── Open Edge in App Mode ────────────────────────────────────────────────────
if ($AppMode) {
    $profileDir = Join-Path $EABMS_ROOT "browser_profiles\$Account"
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    $edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    if (-not (Test-Path $edgePath)) { $edgePath = 'C:\Program Files\Microsoft\Edge\Application\msedge.exe' }
    if (Test-Path $edgePath) {
        Start-Process $edgePath @(
            "--app=http://127.0.0.1:$Port/",
            "--user-data-dir=$profileDir",
            '--no-first-run', '--disable-extensions'
        )
        Write-Host "  Edge opened in App Mode." -ForegroundColor Cyan
    }
}
