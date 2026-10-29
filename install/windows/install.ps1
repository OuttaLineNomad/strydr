<#
  Strydr installer for Windows 10 22H2 and Windows 11 (64-bit).

  Turns on WSL 2 and installs Docker Desktop if needed, downloads Strydr, builds it, creates the sign-in and
  the Health Auto Export token, starts it, and writes everything the runner needs to "Strydr details.txt".
  Running it again updates Strydr and keeps the data, the password and the token.

  Start it with "Install Strydr.cmd", or paste into PowerShell:
    irm https://raw.githubusercontent.com/OuttaLineNomad/strydr/main/install/windows/install.ps1 | iex
#>
param([switch]$Resumed)

$ErrorActionPreference = 'Stop'

$Repo      = 'OuttaLineNomad/strydr'
$Branch    = 'main'
$ScriptUrl = "https://raw.githubusercontent.com/$Repo/$Branch/install/windows/install.ps1"
$ZipUrl    = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
$Base      = Join-Path $env:LOCALAPPDATA 'Strydr'
$App       = Join-Path $Base 'app'
$Self      = Join-Path $Base 'install.ps1'
$Secrets   = Join-Path $App 'secrets'
$Desktop   = [Environment]::GetFolderPath('Desktop')
$Details   = Join-Path $Base 'Strydr details.txt'          # the full copy, with the database key
$DeskCopy  = Join-Path $Desktop 'Strydr details.txt'       # without the key (the Desktop may sync to OneDrive)
$IpFile    = Join-Path $Base 'last-address.txt'
$DockerExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$DockerBin = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'
$Volume    = 'strydr_strydr_data'
$Username  = 'runner'
$RunOnce   = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
$ResumeCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Self`" -Resumed"

$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is many times slower with the progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Say([string]$Text) { Write-Host ''; Write-Host "==> $Text" -ForegroundColor Cyan }
function Note([string]$Text) { Write-Host "    $Text" }

function Stop-WithError([string]$Text) {
    Write-Host ''
    Write-Host "Strydr could not be installed: $Text" -ForegroundColor Red
    Write-Host 'Send a photo of this window to whoever gave you Strydr. Running the installer again is safe.'
    Read-Host 'Press Enter to close'
    exit 1
}

# Any error not handled below ends here, with a readable message, instead of closing the window
trap { Stop-WithError $_.Exception.Message }

# Runs a program and stops with its last lines of output when it exits non-zero. Native stderr is kept away
# from $ErrorActionPreference = 'Stop', or Windows PowerShell 5.1 treats progress messages as errors.
function Invoke-Checked([string]$What, [scriptblock]$Command, [switch]$Live) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = & $Command 2>&1 | ForEach-Object { $s = "$_"; if ($Live) { Write-Host "    $s" }; $s }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    if ($code -ne 0) {
        $tail = ($lines | Select-Object -Last 15) -join "`n"
        Stop-WithError "$What failed (exit code $code).`n$tail"
    }
    return $lines
}

# Runs a program for its exit code only
function Test-Native([scriptblock]$Command) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false } finally { $ErrorActionPreference = $old }
}

function Test-Docker { Test-Native { docker info } }

function Get-IanaTimeZone {
    $map = @{
        'Eastern Standard Time' = 'America/New_York'; 'US Eastern Standard Time' = 'America/Indiana/Indianapolis'
        'Central Standard Time' = 'America/Chicago'; 'Mountain Standard Time' = 'America/Denver'
        'US Mountain Standard Time' = 'America/Phoenix'; 'Pacific Standard Time' = 'America/Los_Angeles'
        'Alaskan Standard Time' = 'America/Anchorage'; 'Hawaiian Standard Time' = 'Pacific/Honolulu'
        'Atlantic Standard Time' = 'America/Halifax'; 'Newfoundland Standard Time' = 'America/St_Johns'
        'Canada Central Standard Time' = 'America/Regina'; 'Central Standard Time (Mexico)' = 'America/Mexico_City'
        'SA Pacific Standard Time' = 'America/Bogota'; 'E. South America Standard Time' = 'America/Sao_Paulo'
        'Argentina Standard Time' = 'America/Argentina/Buenos_Aires'
        'GMT Standard Time' = 'Europe/London'; 'Greenwich Standard Time' = 'Atlantic/Reykjavik'
        'W. Europe Standard Time' = 'Europe/Berlin'; 'Romance Standard Time' = 'Europe/Paris'
        'Central Europe Standard Time' = 'Europe/Budapest'; 'Central European Standard Time' = 'Europe/Warsaw'
        'GTB Standard Time' = 'Europe/Bucharest'; 'FLE Standard Time' = 'Europe/Kyiv'
        'E. Europe Standard Time' = 'Europe/Chisinau'; 'Russian Standard Time' = 'Europe/Moscow'
        'Turkey Standard Time' = 'Europe/Istanbul'; 'Israel Standard Time' = 'Asia/Jerusalem'
        'South Africa Standard Time' = 'Africa/Johannesburg'; 'Arabian Standard Time' = 'Asia/Dubai'
        'India Standard Time' = 'Asia/Kolkata'; 'China Standard Time' = 'Asia/Shanghai'
        'Singapore Standard Time' = 'Asia/Singapore'; 'Tokyo Standard Time' = 'Asia/Tokyo'
        'Korea Standard Time' = 'Asia/Seoul'; 'AUS Eastern Standard Time' = 'Australia/Sydney'
        'E. Australia Standard Time' = 'Australia/Brisbane'; 'Cen. Australia Standard Time' = 'Australia/Adelaide'
        'W. Australia Standard Time' = 'Australia/Perth'; 'New Zealand Standard Time' = 'Pacific/Auckland'
        'UTC' = 'UTC'
    }
    $id = (Get-TimeZone).Id
    if ($map.ContainsKey($id)) { return $map[$id] }
    return 'UTC'
}

function New-Password {
    # 16 characters from an alphabet without look-alikes (no 0/o, 1/l/i), shown as four groups of four
    $alphabet = 'abcdefghjkmnpqrstuvwxyz23456789'.ToCharArray()
    $bytes = New-Object byte[] 16
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $chars = $bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] }
    return (0..3 | ForEach-Object { -join $chars[($_ * 4)..($_ * 4 + 3)] }) -join '-'
}

function New-HexKey {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

function Write-Ascii([string]$Path, [string]$Text) { [IO.File]::WriteAllText($Path, $Text, [Text.Encoding]::ASCII) }
function Write-Utf8([string]$Path, [string]$Text) { [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false)) }

function Get-LanAddress {
    # The home network adapter: up, with a gateway, not a VPN or virtual switch, lowest metric first
    $skip = 'VPN|Virtual|Hyper-V|vEthernet|WSL|TAP|WireGuard|Tailscale|ZeroTier|Loopback'
    $cfg = Get-NetIPConfiguration |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' -and $_.InterfaceDescription -notmatch $skip -and $_.InterfaceAlias -notmatch $skip } |
        Sort-Object { $_.NetIPv4Interface.InterfaceMetric } | Select-Object -First 1
    if ($cfg) { return ($cfg.IPv4Address | Select-Object -First 1).IPAddress }
    return '<this PC''s address>'
}

function New-Shortcut([string]$Path, [string]$Target) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($Path)
    $lnk.TargetPath = $Target
    $lnk.Save()
}

function Get-DetailsText([string]$Ip, [string]$Password, [string]$Token, [string]$KeyBlock) {
    return @"
STRYDR - keep this file private. Anyone with it can read your training data.

Open Strydr
  On this PC:           http://localhost:8080   (or the Strydr icon on the Desktop)
  On your phone/others: http://${Ip}:8080   (on your home Wi-Fi)

Sign in
  Username: $Username
  Password: $Password

Send data from your iPhone (Health Auto Export app; REST API automations may need its paid upgrade)
  Make two automations: one for Workouts, one for Health Metrics. For each one:
    Automation type: REST API
    URL:             http://${Ip}:8081/ingest/hae
    Header:          Authorization   with the value   Bearer $Token
    Export format:   JSON
    Workouts:        include heart rate and route data; choose "Seconds" for time grouping if offered
  Syncs work while the phone is on your home Wi-Fi and this PC is on. Missed syncs catch up later.
  If syncs stop one day, your router may have given this PC a new address: run the installer
  again and this file is updated with the current address.

Import your Apple Health history (optional)
  iPhone: Health app > your picture > Export All Health Data. Send export.zip to this PC.
  Strydr: Settings > Import > choose export.zip.

Keep Strydr running
  Leave this PC on, plugged in and signed in. Docker Desktop starts Strydr when you sign in.
  To update Strydr, run the installer again. Your data, password and token stay the same.
  Check your time zone in Strydr's Settings once.

$KeyBlock
"@
}

# Writes the full copy (with the key) next to Strydr, then a copy without the key to the Desktop
function Write-Details([string]$Ip, [string]$Password, [string]$Token, [string]$Key) {
    $full = Get-DetailsText $Ip $Password $Token @"
Database key (needed to restore a backup; never share it)
  $Key
  Strydr keeps its data inside Docker on this PC. Uninstalling Docker Desktop deletes it.
"@
    Write-Utf8 $Details $full
    try {
        Write-Utf8 $DeskCopy (Get-DetailsText $Ip $Password $Token "Database key: in $Details (kept off the Desktop on purpose).")
    } catch {
        Note "Could not write to the Desktop ($($_.Exception.Message)). Your details are in $Details"
    }
}

# On an update, the phone address in the details files follows the PC's current address
function Update-DetailsAddress([string]$Ip) {
    if (-not (Test-Path $IpFile)) { return }
    $oldIp = (Get-Content -Raw $IpFile).Trim()
    if ($oldIp -and $oldIp -ne $Ip) {
        foreach ($f in $Details, $DeskCopy) {
            if (Test-Path $f) {
                try { Write-Utf8 $f ((Get-Content -Raw $f).Replace("http://${oldIp}:", "http://${Ip}:")) } catch { }
            }
        }
        Note "This PC's address changed from $oldIp to $Ip. Update the URL in both Health Auto Export automations."
    }
}

# ---- 0. Run from a saved copy, as administrator ----------------------------------------------------------------

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $PSCommandPath -or -not $isAdmin) {
    # Under UAC an administrator's token still lists the Administrators group (as deny-only). Without it,
    # elevating would sign in as a different account, and Strydr would be set up for that account instead.
    if (-not ($identity.Groups | Where-Object { $_.Value -eq 'S-1-5-32-544' })) {
        Stop-WithError 'this Windows account is not an administrator. Sign in with an administrator account and run the installer again.'
    }
    New-Item -ItemType Directory -Force -Path $Base | Out-Null
    if (-not $PSCommandPath) {
        Invoke-WebRequest -UseBasicParsing $ScriptUrl -OutFile $Self
    } elseif ($PSCommandPath -ne $Self) {
        Copy-Item -Force $PSCommandPath $Self
    }
    Write-Host 'Strydr needs administrator rights to install. Click "Yes" on the next window.'
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$Self`"")
    if ($Resumed) { $argList += '-Resumed' }
    try {
        Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    } catch {
        # Windows deletes a RunOnce entry before running it, so put it back for the next sign-in
        if ($Resumed) { Set-ItemProperty -Path $RunOnce -Name 'StrydrInstall' -Value $ResumeCmd }
        Stop-WithError 'administrator rights were not given. Run the installer again and click "Yes".'
    }
    exit 0
}

$Host.UI.RawUI.WindowTitle = 'Strydr installer'
Write-Host 'Strydr installer' -ForegroundColor Green
Note 'The first install takes 15 to 40 minutes and may restart the PC once. Leave this window open.'

if (-not [Environment]::Is64BitOperatingSystem) { Stop-WithError 'Strydr needs 64-bit Windows.' }
if ([Environment]::OSVersion.Version.Build -lt 19045) {
    Stop-WithError 'Strydr needs Windows 10 version 22H2 or Windows 11. Run Windows Update first.'
}

# Docker needs hardware virtualization; when it is off in the BIOS, nothing else can work
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
if (-not $cs.HypervisorPresent -and -not $cpu.VirtualizationFirmwareEnabled) {
    Stop-WithError ('virtualization is turned off in this PC''s BIOS/UEFI settings. Turn on "Intel VT-x" or "AMD SVM" ' +
        '(often under Advanced or CPU settings; search the web for your PC model plus "enable virtualization"), then run the installer again.')
}

# ---- 1. WSL 2 and Docker Desktop -------------------------------------------------------------------------------

$needRestart = $false

Say 'Checking Windows features (WSL 2)'
foreach ($feature in 'Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform') {
    if ((Get-WindowsOptionalFeature -Online -FeatureName $feature).State -ne 'Enabled') {
        if ($Resumed) {
            Stop-WithError "the Windows feature $feature is still off after the restart. Install any pending Windows Updates, restart, and run the installer again."
        }
        Note "Turning on $feature..."
        Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart | Out-Null
        $needRestart = $true
    }
}
if (-not $needRestart) {
    Note 'WSL 2 is on. Updating it...'
    Test-Native { wsl.exe --update } | Out-Null
}

Say 'Checking Docker Desktop'
if (-not (Test-Path $DockerExe)) {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $installer = Join-Path $Base 'DockerDesktopInstaller.exe'
    Note 'Downloading Docker Desktop (about 600 MB)...'
    Invoke-WebRequest -UseBasicParsing "https://desktop.docker.com/win/main/$arch/Docker%20Desktop%20Installer.exe" -OutFile $installer
    Note 'Installing Docker Desktop (a few minutes)...'
    $p = Start-Process $installer -ArgumentList 'install', '--quiet', '--accept-license', '--backend=wsl-2' -PassThru
    $null = $p.Handle  # without this, Windows PowerShell often reports no exit code
    $p.WaitForExit()  # not -Wait: in PowerShell 5.1 that also waits for anything the installer leaves running
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { Stop-WithError "the Docker Desktop installer exited with code $($p.ExitCode)." }
    Remove-Item -Force $installer -ErrorAction SilentlyContinue
    $needRestart = $true
} else {
    Note 'Docker Desktop is installed.'
}

# Docker Desktop only lets members of docker-users use it, and a new membership needs a fresh sign-in
if (-not ((& whoami.exe /groups) -match '\\docker-users\b')) {
    Test-Native { net.exe localgroup docker-users "$($identity.Name)" /add } | Out-Null
    if (-not $Resumed) { $needRestart = $true }  # never restart twice in a row; Docker will say if it is still missing
}

# Start Docker Desktop at sign-in, so Strydr comes back after every restart
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'Docker Desktop.lnk'
if (-not (Test-Path $startup)) { New-Shortcut $startup $DockerExe }

if ($needRestart) {
    Set-ItemProperty -Path $RunOnce -Name 'StrydrInstall' -Value $ResumeCmd
    Say 'Windows needs to restart'
    Note 'After the restart, sign in. The installer carries on by itself (click "Yes" when asked).'
    $answer = Read-Host 'Restart now? Type Y and press Enter (or close this window and restart later)'
    if ($answer -match '^[Yy]') { Restart-Computer -Force }
    exit 0
}

Say 'Starting Docker'
$env:Path = "$DockerBin;$env:Path"
if (-not (Test-Docker)) {
    # Through Explorer, so Docker Desktop runs as the signed-in user and not as administrator
    Start-Process explorer.exe -ArgumentList "`"$DockerExe`""
    Note 'Waiting for Docker to start (the first start can take a few minutes).'
    Note 'If Docker shows a welcome screen or asks you to sign in, you can skip it.'
    $deadline = (Get-Date).AddMinutes(10)
    while (-not (Test-Docker)) {
        if ((Get-Date) -gt $deadline) { Stop-WithError 'Docker did not start within 10 minutes. Restart the PC and run the installer again.' }
        Start-Sleep -Seconds 5
    }
}
Note 'Docker is running.'

# ---- 2. Download Strydr ----------------------------------------------------------------------------------------

Say 'Downloading Strydr'
$tmp = Join-Path $env:TEMP ('strydr-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zip = Join-Path $tmp 'strydr.zip'
Invoke-WebRequest -UseBasicParsing $ZipUrl -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$src = Get-ChildItem -Directory $tmp | Select-Object -First 1
New-Item -ItemType Directory -Force -Path $App | Out-Null
# Mirror the code, but never touch the key, the markers or the settings file
& robocopy.exe $src.FullName $App /MIR /XD secrets /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Stop-WithError "copying Strydr failed (robocopy code $LASTEXITCODE)." }
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
$newSelf = Join-Path $App 'install\windows\install.ps1'
if (Test-Path $newSelf) { Copy-Item -Force $newSelf $Self }
Note "Strydr is in $App"

# ---- 3. Key and settings ---------------------------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $Secrets | Out-Null
$keyFile = Join-Path $Secrets 'strydr_db_key'
if (-not (Test-Path $keyFile)) {
    if (Test-Native { docker volume inspect $Volume }) {
        # A new key cannot open the existing data
        Stop-WithError ("Strydr's data is still in Docker, but its database key file is missing. Copy the 64-character " +
            "key from your 'Strydr details.txt' into a file named strydr_db_key in $Secrets (nothing else in the file), then run the installer again.")
    }
    Write-Ascii $keyFile (New-HexKey)
}
$envFile = Join-Path $App '.env'
if (-not (Test-Path $envFile)) {
    Write-Ascii $envFile ("COMPOSE_PROJECT_NAME=strydr`nTZ=" + (Get-IanaTimeZone) + "`n")
}
$ip = Get-LanAddress

# ---- 4. Build, create the sign-in, start -----------------------------------------------------------------------

Push-Location $App
try {
    Say 'Building Strydr (5 to 15 minutes the first time)'
    Invoke-Checked 'Building Strydr' { docker compose build strydr } -Live | Out-Null

    $marker = Join-Path $Secrets '.initialised'
    $fresh = -not (Test-Path $marker)
    if ($fresh) {
        Say 'Creating your sign-in and sync token'
        $password = New-Password
        # The password goes in on stdin, so it is never written to disk. --reset: until the marker exists nobody
        # holds a sign-in, so a half-finished earlier run is simply replaced (the data is kept).
        $out = Invoke-Checked 'Creating the sign-in' {
            $password | docker compose run --rm -T strydr init --reset --username $Username --password-file /dev/stdin
        }
        $token = $out | Where-Object { $_ -match '^[A-Za-z0-9_-]{40,}$' } | Select-Object -Last 1
        if (-not $token) { Stop-WithError 'the sync token was not printed.' }
        # Shown at once, so nothing that fails later can lose them
        Note "Username: $Username"
        Note "Password: $password"
        Note "Sync token: $token"
        Write-Details $ip $password $token (Get-Content -Raw $keyFile).Trim()
        Write-Ascii $marker (Get-Date -Format s)  # only once the details file exists
    } else {
        Update-DetailsAddress $ip
    }
    Write-Ascii $IpFile $ip

    Say 'Starting Strydr'
    Invoke-Checked 'Starting Strydr' { docker compose up -d --remove-orphans strydr } | Out-Null
    $deadline = (Get-Date).AddMinutes(3)
    $up = $false
    while (-not $up -and (Get-Date) -lt $deadline) {
        try { $up = (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8080/api/v1/health' -TimeoutSec 3).StatusCode -eq 200 } catch { Start-Sleep -Seconds 3 }
    }
    if (-not $up) { Stop-WithError 'Strydr did not answer on port 8080 within 3 minutes.' }
    Invoke-Checked 'Cleaning up old images' { docker image prune -f } | Out-Null
} finally { Pop-Location }

# ---- 5. Let the phone reach it on the home network -------------------------------------------------------------

Say 'Letting your iPhone reach Strydr on your home Wi-Fi'
Get-NetFirewallRule -DisplayName 'Strydr' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'Strydr' -Direction Inbound -Protocol TCP -LocalPort 8080, 8081 -Action Allow -Profile Private | Out-Null
# A cancelled Windows Firewall prompt leaves Block rules for Docker's programs, and Block beats Allow
$dockerDir = Join-Path $env:ProgramFiles 'Docker'
Get-NetFirewallRule -Direction Inbound -Action Block -ErrorAction SilentlyContinue | Where-Object {
    ($_ | Get-NetFirewallApplicationFilter).Program -like "$dockerDir\*"
} | Disable-NetFirewallRule
$net = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -eq 'Internet' } | Select-Object -First 1
if ($net -and $net.NetworkCategory -eq 'Public') {
    Note "Windows treats the network '$($net.Name)' as public, which blocks your phone."
    $answer = Read-Host 'Is this your home network? Type Y to mark it as private (trusted)'
    if ($answer -match '^[Yy]') {
        Set-NetConnectionProfile -InterfaceIndex $net.InterfaceIndex -NetworkCategory Private
        Note 'Marked as private.'
    } else {
        Note 'Left as public. Your phone cannot sync until this PC is on a private network.'
    }
}
# Never sleep while plugged in, or syncs fail while the PC sleeps
& powercfg.exe /change standby-timeout-ac 0 | Out-Null
Note 'Sleep is off while the PC is plugged in (Settings > System > Power to change it).'

try { Write-Ascii (Join-Path $Desktop 'Strydr.url') "[InternetShortcut]`r`nURL=http://localhost:8080/`r`n" } catch { }

# ---- 6. Done ---------------------------------------------------------------------------------------------------

$shown = if (Test-Path $DeskCopy) { $DeskCopy } else { $Details }
if ($fresh) {
    Say 'Done! Strydr is running.'
    Note "Your sign-in, sync token and phone setup steps are in: $shown"
    Note "The copy with your database key is in: $Details"
    Start-Process notepad.exe "`"$shown`""
} else {
    Say 'Done! Strydr is updated and running.'
    Note "Your sign-in and token have not changed. They are in: $shown"
    Note "Address for your phone: http://${ip}:8080   Sync URL: http://${ip}:8081/ingest/hae"
}
Start-Process 'http://localhost:8080/'
Read-Host 'Press Enter to close this window'
