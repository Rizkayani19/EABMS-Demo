# ==============================================================================
# ENTERPRISE ACCOUNTS & BUSINESS MANAGEMENT SYSTEM (EABMS)
# APPLICATION UNINSTALLER
# ==============================================================================
# Safely removes EABMS application processes, shortcuts, autoruns, scheduled
# tasks and (optionally, after confirmation) the application folder.
#
# GUARANTEE - the following are 100% PRESERVED:
#   - PostgreSQL server, Windows service, data directory
#   - All PostgreSQL databases (eabms_ngl, eabms_ewf, eabms_cpf, abms_*, ...)
#   - Python installation and the shared virtual environment (D:\ABMS\...\venv)
#   - The original ABMS installation (D:\ABMS) and its ports 8010-8012
# ==============================================================================

[CmdletBinding()]
param(
    [string]$AppRoot = "",
    [switch]$FromBatch,
    [switch]$DryRun,
    [switch]$Silent,
    [switch]$RemoveFolder,
    [switch]$KeepFolder
)

$ErrorActionPreference = 'Continue'

# ------------------------------------------------------------------------------
# Resolve application root
# ------------------------------------------------------------------------------
if (-not $AppRoot) {
    # Normal location: <AppRoot>\DEPLOYMENT\Windows\Uninstall-EABMS.ps1
    $candidate = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if ($candidate -and (Test-Path (Join-Path $candidate '02_Backend\manage.py'))) {
        $AppRoot = $candidate
    } else {
        $AppRoot = 'D:\EABMS'
    }
}
$AppRoot = [System.IO.Path]::GetFullPath($AppRoot).TrimEnd('\')

# EABMS-specific identifiers (deliberately NOT a bare "ABMS" so the original
# ABMS installation is never matched).
$AppName       = 'EABMS'
$AppPorts      = @(8020, 8021, 8022)
$NamePatterns  = @('EABMS', 'Enterprise Accounts', 'NexGen Holdings', 'Employee Welfare Fund', 'Corporate Provident Fund')
$PreservedDbs  = @('eabms_ngl', 'eabms_ewf', 'eabms_cpf')
$SharedPython  = 'D:\ABMS\02_Backend\venv\Scripts\python.exe'

# ------------------------------------------------------------------------------
# 1. Administrator check & auto-elevation (skipped when launched from the .bat,
#    which is already elevated, or in dry-run mode)
# ------------------------------------------------------------------------------
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $FromBatch -and -not $DryRun) {
    try {
        Write-Host "[*] Requesting Administrator Privileges..." -ForegroundColor Yellow
        $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -AppRoot `"$AppRoot`""
        if ($Silent)       { $argList += " -Silent" }
        if ($RemoveFolder) { $argList += " -RemoveFolder" }
        if ($KeepFolder)   { $argList += " -KeepFolder" }
        Start-Process powershell.exe -ArgumentList $argList -Verb RunAs -ErrorAction Stop
        exit
    } catch {
        Write-Host "[!] Administrator prompt unavailable or declined. Proceeding with user privileges." -ForegroundColor DarkYellow
    }
}

# Never hold a lock on the app folder
Set-Location "$env:SystemDrive\"

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
function Test-SafeAppRoot([string]$path) {
    if (-not $path) { return $false }
    $driveRoot = [System.IO.Path]::GetPathRoot($path).TrimEnd('\')
    if ($path.TrimEnd('\') -ieq $driveRoot) { return $false }          # never a drive root
    $forbidden = @($env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)},
                   $env:ProgramData, $env:USERPROFILE, "$env:SystemDrive\Users",
                   'D:\ABMS')                                            # never the original ABMS
    foreach ($f in $forbidden) {
        if ($f -and ($path.TrimEnd('\') -ieq $f.TrimEnd('\'))) { return $false }
    }
    if ($path -match 'PostgreSQL') { return $false }
    return (Test-Path (Join-Path $path '02_Backend\manage.py'))
}

function Test-NameMatch([string]$text) {
    if (-not $text) { return $false }
    foreach ($p in $NamePatterns) { if ($text -like "*$p*") { return $true } }
    return $false
}

function Test-PathMatch([string]$text) {
    if (-not $text) { return $false }
    return ($text -like "*$AppRoot\*" -or $text -like "*$AppRoot`"*" -or $text.TrimEnd('\') -ieq $AppRoot)
}

$wsh = $null
try { $wsh = New-Object -ComObject WScript.Shell } catch {}

function Test-AppShortcut($lnkFile) {
    if (Test-NameMatch $lnkFile.BaseName) { return $true }
    if ($wsh) {
        try {
            $s = $wsh.CreateShortcut($lnkFile.FullName)
            foreach ($v in @($s.TargetPath, $s.Arguments, $s.WorkingDirectory)) {
                if (Test-PathMatch $v) { return $true }
            }
        } catch {}
    }
    return $false
}

function Remove-Target([string]$path, [string]$label, [switch]$Recurse) {
    if ($DryRun) {
        Write-Host "      [WHATIF] Would remove $label : $path" -ForegroundColor Gray
        return
    }
    if ($Recurse) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue }
    else          { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "      [+] Removed $label : $path" -ForegroundColor Green
    } else {
        Write-Host "      [!] Could not remove $label : $path" -ForegroundColor Yellow
    }
}

# Read DB credentials from .env (before the folder may be deleted) so the final
# report can confirm the databases are still present.
$dbUser = 'postgres'; $dbPass = $null; $dbHost = 'localhost'; $dbPort = '5432'
$envFile = Join-Path $AppRoot '02_Backend\.env'
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile -ErrorAction SilentlyContinue) {
        if ($line -match '^\s*DB_USER\s*=\s*(.+)$')     { $dbUser = $Matches[1].Trim() }
        if ($line -match '^\s*DB_PASSWORD\s*=\s*(.+)$') { $dbPass = $Matches[1].Trim() }
        if ($line -match '^\s*DB_HOST\s*=\s*(.+)$')     { $dbHost = $Matches[1].Trim() }
        if ($line -match '^\s*DB_PORT\s*=\s*(.+)$')     { $dbPort = $Matches[1].Trim() }
    }
}

# ------------------------------------------------------------------------------
# Banner
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "        ENTERPRISE ACCOUNTS & BUSINESS MANAGEMENT SYSTEM            " -ForegroundColor Yellow
Write-Host "                   EABMS APPLICATION UNINSTALLER                    " -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Target Folder : $AppRoot" -ForegroundColor Gray
Write-Host " Server Ports  : $($AppPorts -join ', ')" -ForegroundColor Gray
Write-Host ""
Write-Host " This uninstaller will remove:" -ForegroundColor Yellow
Write-Host "   [1] Running EABMS servers (NGL / EWF / CPF) and EABMS app windows" -ForegroundColor White
Write-Host "   [2] EABMS scheduled tasks and Windows services (if any)" -ForegroundColor White
Write-Host "   [3] Windows Startup and Registry autorun entries" -ForegroundColor White
Write-Host "   [4] Desktop and Start Menu shortcuts" -ForegroundColor White
Write-Host "   [5] Programs & Features registration (if any)" -ForegroundColor White
Write-Host "   [6] Application folder $AppRoot  (ONLY if you confirm)" -ForegroundColor White
Write-Host ""
Write-Host " ==================== STRICT SAFEGUARDS ====================" -ForegroundColor Green
Write-Host "   [+] PostgreSQL server and service will NOT be touched." -ForegroundColor Green
Write-Host "   [+] Databases ($($PreservedDbs -join ', ')) will NOT be modified or deleted." -ForegroundColor Green
Write-Host "   [+] Python and the shared virtual environment will NOT be touched." -ForegroundColor Green
Write-Host "   [+] The original ABMS installation (D:\ABMS) will NOT be touched." -ForegroundColor Green
Write-Host " ============================================================" -ForegroundColor Green
Write-Host ""

if ($DryRun) {
    Write-Host " [!] DRY-RUN MODE: No changes or deletions will be made." -ForegroundColor Magenta
    Write-Host ""
} elseif (-not $FromBatch -and -not $Silent) {
    $confirm = Read-Host " Are you sure you want to uninstall EABMS [Y/N]? (Default: N)"
    if ($confirm.Trim().ToUpper() -ne "Y") {
        Write-Host ""
        Write-Host " Uninstallation cancelled by user." -ForegroundColor Yellow
        exit 0
    }
    Write-Host ""
}

# ------------------------------------------------------------------------------
# STEP 1: STOP EABMS PROCESSES
# ------------------------------------------------------------------------------
Write-Host "[1/6] Stopping EABMS servers and app windows..." -ForegroundColor Cyan

function Test-ProtectedProcess($p) {
    if (-not $p) { return $true }
    $name = "$($p.Name)"; $cmd = "$($p.CommandLine)"
    if ($p.ProcessId -le 4 -or $p.ProcessId -eq $PID) { return $true }
    if ($name -match 'postgres|pg_ctl' -or $cmd -match 'postgres|pg_ctl') { return $true }
    if ($cmd -match 'Uninstall[-_]EABMS' -or $cmd -match 'antigravity') { return $true }
    return $false
}

$stopped = 0
# 1a. By port (servers run with D:\ABMS venv python, so their command line
#     does not contain the EABMS folder)
foreach ($port in $AppPorts) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $owners) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
        if (Test-ProtectedProcess $p) { continue }
        if ($DryRun) {
            Write-Host "      [WHATIF] Would stop $($p.Name) (PID $procId) listening on port $port" -ForegroundColor Gray
        } else {
            Write-Host "      [*] Stopping $($p.Name) (PID $procId) on port $port..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $stopped++
        }
    }
}

# 1b. By folder reference (launcher scripts, Edge/Chrome app windows using the
#     EABMS browser profile, any process started from the folder)
$targetNames = @('python', 'pythonw', 'waitress', 'wscript', 'cscript', 'cmd', 'powershell', 'pwsh', 'msedge', 'chrome')
$procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $base = $_.Name.ToLower().Replace('.exe', '')
    ($targetNames -contains $base) -and
    ((Test-PathMatch $_.CommandLine) -or (Test-PathMatch $_.ExecutablePath)) -and
    -not (Test-ProtectedProcess $_)
}
foreach ($p in $procs) {
    if ($DryRun) {
        Write-Host "      [WHATIF] Would stop $($p.Name) (PID $($p.ProcessId))" -ForegroundColor Gray
    } else {
        Write-Host "      [*] Stopping $($p.Name) (PID $($p.ProcessId))..." -ForegroundColor Yellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}
if (-not $DryRun -and $stopped -gt 0) { Start-Sleep -Seconds 2 }
Write-Host "      [+] EABMS processes stopped ($stopped). PostgreSQL and ABMS untouched." -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 2: SCHEDULED TASKS & WINDOWS SERVICES
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/6] Checking EABMS Scheduled Tasks and Services..." -ForegroundColor Cyan

$tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    ($_.TaskName -match 'EABMS' -or $_.TaskPath -match 'EABMS' -or
     ($_.Actions | Where-Object { (Test-PathMatch $_.Execute) -or (Test-PathMatch $_.Arguments) })) -and
    $_.TaskName -notmatch 'postgres'
}
if ($tasks) {
    foreach ($t in $tasks) {
        if ($DryRun) {
            Write-Host "      [WHATIF] Would unregister task: $($t.TaskPath)$($t.TaskName)" -ForegroundColor Gray
        } else {
            Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false -ErrorAction SilentlyContinue
            Write-Host "      [+] Removed task: $($t.TaskPath)$($t.TaskName)" -ForegroundColor Green
        }
    }
} else {
    Write-Host "      [i] No EABMS scheduled tasks found." -ForegroundColor Gray
}

$services = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'EABMS' -or $_.DisplayName -match 'EABMS' -or (Test-PathMatch $_.PathName)
}
foreach ($svc in $services) {
    if ($svc.Name -match 'postgres' -or $svc.DisplayName -match 'postgres' -or $svc.PathName -match 'postgres') {
        Write-Host "      [i] PRESERVING PostgreSQL service: $($svc.Name)" -ForegroundColor Green
        continue
    }
    if ($DryRun) {
        Write-Host "      [WHATIF] Would remove service: $($svc.Name)" -ForegroundColor Gray
    } else {
        if ($svc.State -eq 'Running') { Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue }
        & sc.exe delete $svc.Name 2>&1 | Out-Null
        Write-Host "      [+] Removed service: $($svc.Name)" -ForegroundColor Green
    }
}
if (-not $services) { Write-Host "      [i] No EABMS services found." -ForegroundColor Gray }

# ------------------------------------------------------------------------------
# STEP 3: STARTUP & REGISTRY AUTORUN ENTRIES
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/6] Removing Windows Startup and Autorun entries..." -ForegroundColor Cyan

$regRunKeys = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
)
foreach ($key in $regRunKeys) {
    if (-not (Test-Path $key)) { continue }
    $item = Get-Item -Path $key -ErrorAction SilentlyContinue
    foreach ($valName in $item.GetValueNames()) {
        $data = "$($item.GetValue($valName))"
        if ((Test-NameMatch $valName) -or (Test-PathMatch $data)) {
            if ($DryRun) {
                Write-Host "      [WHATIF] Would remove autorun '$valName' from $key" -ForegroundColor Gray
            } else {
                Remove-ItemProperty -Path $key -Name $valName -Force -ErrorAction SilentlyContinue
                Write-Host "      [+] Removed autorun '$valName' ($key)" -ForegroundColor Green
            }
        }
    }
}

$startupDirs = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
)
foreach ($dir in $startupDirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -Force -ErrorAction SilentlyContinue |
        Where-Object { ($_.Extension -eq '.lnk' -and (Test-AppShortcut $_)) -or
                       ($_.Extension -in '.bat', '.vbs', '.cmd' -and (Test-NameMatch $_.Name)) } |
        ForEach-Object { Remove-Target $_.FullName 'startup item' }
}
Write-Host "      [+] Startup and autorun cleanup complete." -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 4: DESKTOP & START MENU SHORTCUTS
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/6] Removing Desktop and Start Menu shortcuts..." -ForegroundColor Cyan

$desktopDirs = @([Environment]::GetFolderPath('Desktop'), "$env:USERPROFILE\Desktop", "$env:PUBLIC\Desktop") |
               Where-Object { $_ } | Select-Object -Unique
foreach ($dir in $desktopDirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -Filter '*.lnk' -Force -ErrorAction SilentlyContinue |
        Where-Object { Test-AppShortcut $_ } |
        ForEach-Object { Remove-Target $_.FullName 'desktop shortcut' }
}

$startMenuRoots = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs"
)
foreach ($smRoot in $startMenuRoots) {
    if (-not (Test-Path $smRoot)) { continue }
    # Whole EABMS program folders
    Get-ChildItem -Path $smRoot -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { Test-NameMatch $_.Name } |
        ForEach-Object { Remove-Target $_.FullName 'Start Menu folder' -Recurse }
    # Loose shortcuts anywhere else in the Start Menu (excluding Startup, done above)
    Get-ChildItem -Path $smRoot -Filter '*.lnk' -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\Startup\\' -and (Test-AppShortcut $_) } |
        ForEach-Object { Remove-Target $_.FullName 'Start Menu shortcut' }
}
Write-Host "      [+] Shortcut cleanup complete." -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 5: PROGRAMS & FEATURES REGISTRATION
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[5/6] Checking Programs and Features registration..." -ForegroundColor Cyan

$uninstallKeys = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
)
$foundReg = $false
foreach ($uk in $uninstallKeys) {
    if (-not (Test-Path $uk)) { continue }
    Get-ChildItem -Path $uk -ErrorAction SilentlyContinue | ForEach-Object {
        $props = Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue
        if ($props -and ((Test-NameMatch $props.DisplayName) -or (Test-PathMatch $props.InstallLocation)) -and
            "$($props.DisplayName)" -notmatch 'PostgreSQL|Python') {
            $foundReg = $true
            Remove-Target $_.PSPath "registration '$($props.DisplayName)'" -Recurse
        }
    }
}
if (-not $foundReg) { Write-Host "      [i] No Programs and Features entry found." -ForegroundColor Gray }

# ------------------------------------------------------------------------------
# STEP 6: APPLICATION FOLDER (ONLY WITH CONFIRMATION)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[6/6] Application folder ($AppRoot)..." -ForegroundColor Cyan

$folderRemoved = $false
$folderKept    = $false

if (-not (Test-Path -LiteralPath $AppRoot)) {
    Write-Host "      [i] Application folder does not exist." -ForegroundColor Gray
    $folderRemoved = $true
} elseif (-not (Test-SafeAppRoot $AppRoot)) {
    Write-Host "      [!] SAFETY STOP: '$AppRoot' does not look like an EABMS folder" -ForegroundColor Red
    Write-Host "          (02_Backend\manage.py missing, or it is a protected location)." -ForegroundColor Red
    Write-Host "          The folder was NOT deleted." -ForegroundColor Red
    $folderKept = $true
} else {
    $doRemove = $false
    if ($RemoveFolder)     { $doRemove = $true }
    elseif ($KeepFolder)   { $doRemove = $false }
    elseif ($Silent)       { $doRemove = $false }
    else {
        Write-Host ""
        Write-Host "      The folder contains the application code, logs, local backup" -ForegroundColor Yellow
        Write-Host "      files and browser profiles. Database records live in PostgreSQL" -ForegroundColor Yellow
        Write-Host "      and are NOT stored in this folder - they will remain intact." -ForegroundColor Yellow
        Write-Host ""
        $ans = Read-Host "      Do you also want to DELETE the folder '$AppRoot' from this computer? [Y/N] (Default: N)"
        $doRemove = ($ans.Trim().ToUpper() -eq 'Y')
    }

    if (-not $doRemove) {
        Write-Host "      [i] Folder kept at $AppRoot (you can delete it manually later)." -ForegroundColor Gray
        $folderKept = $true
    } elseif ($DryRun) {
        Write-Host "      [WHATIF] Would delete folder: $AppRoot" -ForegroundColor Gray
    } else {
        Set-Location "$env:SystemDrive\"
        Write-Host "      [*] Deleting $AppRoot ..." -ForegroundColor Yellow
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Remove-Item -LiteralPath $AppRoot -Recurse -Force -ErrorAction Stop
            } catch {
                Start-Sleep -Seconds 1
                & cmd.exe /c "rd /s /q `"$AppRoot`"" 2>&1 | Out-Null
            }
            if (-not (Test-Path -LiteralPath $AppRoot)) { break }
        }
        if (-not (Test-Path -LiteralPath $AppRoot)) {
            Write-Host "      [+] Application folder deleted." -ForegroundColor Green
            $folderRemoved = $true
        } else {
            Write-Host "      [!] Some files could not be deleted (possibly open in an editor/Explorer)." -ForegroundColor Yellow
            Get-ChildItem -LiteralPath $AppRoot -Recurse -Force -ErrorAction SilentlyContinue |
                Select-Object -First 5 | ForEach-Object { Write-Host "          - $($_.FullName)" -ForegroundColor Gray }
        }
    }
}

# ------------------------------------------------------------------------------
# VERIFICATION & PRESERVATION REPORT
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "                 EABMS UNINSTALLATION SUMMARY                       " -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

$pgService = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*postgres*' -or $_.DisplayName -like '*postgres*' } | Select-Object -First 1
if ($pgService) {
    Write-Host "  [+] PostgreSQL Service ($($pgService.Name)): $($pgService.State) (PRESERVED)" -ForegroundColor Green
} else {
    Write-Host "  [+] PostgreSQL: not touched by this uninstaller." -ForegroundColor Green
}

# Confirm databases still exist (if psql and credentials are available)
$psql = Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
if ($psql -and $dbPass) {
    $env:PGPASSWORD = $dbPass
    $dbList = & $psql.FullName -U $dbUser -h $dbHost -p $dbPort -At -c "SELECT datname FROM pg_database" 2>$null
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    foreach ($db in $PreservedDbs) {
        if ($dbList -contains $db) {
            Write-Host "  [+] Database $db : PRESENT (PRESERVED)" -ForegroundColor Green
        } else {
            Write-Host "  [i] Database $db : not found on server (was never created / not touched)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "  [+] Databases ($($PreservedDbs -join ', ')): NOT touched (100% PRESERVED)" -ForegroundColor Green
}

if (Test-Path $SharedPython) {
    Write-Host "  [+] Python virtual environment ($SharedPython): PRESERVED" -ForegroundColor Green
} else {
    Write-Host "  [+] Python installation: NOT touched" -ForegroundColor Green
}
if (Test-Path 'D:\ABMS') {
    Write-Host "  [+] Original ABMS installation (D:\ABMS): PRESERVED" -ForegroundColor Green
}

if ($DryRun) {
    Write-Host ""
    Write-Host "  [i] Dry-run completed. Nothing was changed." -ForegroundColor Magenta
} else {
    if ($folderRemoved)   { Write-Host "  [+] EABMS Files ($AppRoot): Completely Removed" -ForegroundColor Green }
    elseif ($folderKept)  { Write-Host "  [i] EABMS Files ($AppRoot): Kept on disk (by choice / safety)" -ForegroundColor Gray }
    else                  { Write-Host "  [!] EABMS Files ($AppRoot): Partially Removed (check locked files)" -ForegroundColor Yellow }
    Write-Host "  [+] EABMS Processes, Shortcuts, Tasks and Autoruns: Removed" -ForegroundColor Green
    Write-Host ""
    Write-Host "====================================================================" -ForegroundColor Green
    Write-Host "  [+] EABMS APPLICATION HAS BEEN UNINSTALLED SUCCESSFULLY!          " -ForegroundColor Green
    Write-Host "====================================================================" -ForegroundColor Green
}
Write-Host ""
