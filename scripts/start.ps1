<#
Starts the API and the static web build, and waits for both to answer.

PowerShell rather than batch, because the project path contains spaces
("AppData\Local\Programs\Antigravity IDE") and nested quoting in a .bat
silently fails to start the servers. Self-elevates so it can open the
firewall port, which a phone on the same network needs.

Ctrl-C, or closing this window, stops both.
#>
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 8000,
    [switch]$NoTunnel
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# App and API share one origin on one port, so a single tunnel covers both and
# the client never needs a host baked into its bundle.
$AppPort = $WebPort

# --- firewall (needs admin) --------------------------------------------------
Write-Host ''
if ($isAdmin) {
    Write-Host "  Firewall: opening port $ApiPort..." -ForegroundColor DarkGray
    netsh advfirewall firewall delete rule name="Vedic Chart dev" 2>&1 | Out-Null
    $res = netsh advfirewall firewall add rule name="Vedic Chart dev" `
        dir=in action=allow protocol=TCP localport="$ApiPort" profile=private,domain 2>&1
    if ($res -match 'Ok\.') {
        Write-Host '  Firewall rule added.' -ForegroundColor Green
    } else {
        Write-Host '  Firewall rule failed. A phone on this network may not connect.' -ForegroundColor Yellow
    }
} else {
    Write-Host '  Not running as admin, so the firewall port was not opened.' -ForegroundColor Yellow
    Write-Host '  A public tunnel will still work. For LAN access, right-click start.bat' -ForegroundColor Yellow
    Write-Host '  and choose "Run as administrator".' -ForegroundColor Yellow
}

# --- build if needed ---------------------------------------------------------
$dist = Join-Path $root 'mobile\dist'
if (-not (Test-Path (Join-Path $dist 'index.html'))) {
    Write-Host '  No web build found. Building it (takes a minute)...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'mobile')
    & npx expo export --platform web
    Pop-Location
} else {
    Write-Host '  Web build present.' -ForegroundColor DarkGray
}

# --- start the server (serves both the app and the API) ----------------------
$api = $null
$web = $null

Write-Host "  Starting server on port $AppPort..." -ForegroundColor DarkGray
$api = Start-Process -FilePath 'python' `
    -ArgumentList '-m', 'uvicorn', 'api.server:app', '--host', '0.0.0.0', "--port", $AppPort `
    -WorkingDirectory $root -PassThru -WindowStyle Minimized

function Test-Ready($url) {
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            if ((Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) {
                return $true
            }
        } catch { }
    }
    return $false
}

$serverOk = Test-Ready "http://localhost:$AppPort/health"
$appOk = Test-Ready "http://localhost:$AppPort/"

$lan = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } |
    Select-Object -First 1).IPAddress

# --- public tunnel -----------------------------------------------------------
$publicUrl = $null
$tunnel = $null
if (-not $NoTunnel) {
    Write-Host '  Starting public tunnel...' -ForegroundColor DarkGray
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        foreach ($candidate in @(
            'C:\Program Files (x86)\cloudflared\cloudflared.exe',
            'C:\Program Files\cloudflared\cloudflared.exe')) {
            if (Test-Path $candidate) { $cf = $candidate; break }
        }
    }
    if ($cf) {
        $tlog = Join-Path $env:TEMP 'vedic-tunnel.err'
        Remove-Item $tlog -Force -ErrorAction SilentlyContinue
        $tunnel = Start-Process -FilePath $cf `
            -ArgumentList 'tunnel', '--url', "http://localhost:$AppPort", '--no-autoupdate' `
            -RedirectStandardError $tlog -PassThru -WindowStyle Minimized

        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Seconds 1
            $m = Select-String -Path $tlog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' `
                -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) {
                $publicUrl = ([regex]::Match($m.Line, 'https://[a-z0-9-]+\.trycloudflare\.com')).Value
                break
            }
        }
    } else {
        Write-Host '  cloudflared not found, skipping the tunnel.' -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host '  ============================================' -ForegroundColor Green
Write-Host '   Vedic Chart' -ForegroundColor Green
Write-Host '  ============================================' -ForegroundColor Green
Write-Host ''
if ($appOk) {
    Write-Host "   This PC:  http://localhost:$AppPort" -ForegroundColor White
    if ($lan) { Write-Host "   LAN:      http://$lan`:$AppPort" -ForegroundColor White }
} else {
    Write-Host "   App FAILED to start. Is something already on port $AppPort?" -ForegroundColor Red
}
if ($serverOk) {
    Write-Host "   API docs: http://localhost:$AppPort/docs" -ForegroundColor White
} else {
    Write-Host "   API FAILED to start." -ForegroundColor Red
}
if ($publicUrl) {
    Write-Host ''
    Write-Host '   Share this link:' -ForegroundColor DarkGray
    Write-Host "   $publicUrl" -ForegroundColor Cyan
} elseif (-not $NoTunnel) {
    Write-Host '   Tunnel did not come up; check the log.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host '   No authentication on that link. Anyone with it can create' -ForegroundColor DarkGray
Write-Host '   profiles. Stop this when you are done testing.' -ForegroundColor DarkGray
Write-Host ''
Write-Host '   Keep this window open. Press Ctrl-C to stop everything.' -ForegroundColor DarkGray
Write-Host ''

try {
    while ($true) { Start-Sleep -Seconds 2 }
} finally {
    foreach ($p in @($tunnel, $web, $api)) {
        if ($p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host '  Stopped.' -ForegroundColor DarkGray
}
