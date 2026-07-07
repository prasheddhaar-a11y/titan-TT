#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Hardens IIS/Windows Schannel TLS configuration.

.DESCRIPTION
    VAPT Fix #26 — Weak or Vulnerable SSL/TLS Cipher Suites Detected
    VAPT Fix #34 — Weak Ciphers/Encoding

    Applies Windows Registry changes under SCHANNEL to:
      1. Disable SSL 2.0, SSL 3.0, TLS 1.0, TLS 1.1 (all weak/deprecated)
      2. Enable  TLS 1.2 and TLS 1.3
      3. Disable weak/export cipher suites (RC4, DES, 3DES, NULL, export)
      4. Enable  strong cipher suites (AES-128-GCM, AES-256-GCM, CHACHA20)
      5. Set cipher-suite priority ordering per BSI TR-02102-2 / NIST SP 800-52r2

    IMPORTANT: A server restart is required for registry changes to take effect.

.NOTES
    Run this script once from an elevated PowerShell session on the IIS host.
    Test with testssl.sh or Qualys SSL Labs after applying to verify Grade A.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SchannelBase = 'HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL'

function Set-SchannelProtocol {
    param (
        [string]$Protocol,
        [bool]$ClientEnabled,
        [bool]$ServerEnabled
    )
    $basePath = "$SchannelBase\Protocols\$Protocol"
    foreach ($side in @('Client', 'Server')) {
        $path = "$basePath\$side"
        if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }
        $enabled = if ($side -eq 'Server') { $ServerEnabled } else { $ClientEnabled }
        $value   = if ($enabled) { 1 } else { 0 }
        $disabledDefault = if ($enabled) { 0 } else { 1 }
        Set-ItemProperty -Path $path -Name 'Enabled'        -Value $value          -Type DWord
        Set-ItemProperty -Path $path -Name 'DisabledByDefault' -Value $disabledDefault -Type DWord
        Write-Host "  $Protocol\$side : Enabled=$value  DisabledByDefault=$disabledDefault"
    }
}

function Set-CipherEnabled {
    param (
        [string]$Cipher,
        [bool]$Enabled
    )
    $path = "$SchannelBase\Ciphers\$Cipher"
    if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }
    $value = if ($Enabled) { 0xFFFFFFFF } else { 0 }
    Set-ItemProperty -Path $path -Name 'Enabled' -Value $value -Type DWord
    Write-Host "  Cipher $Cipher : Enabled=$Enabled"
}

function Set-HashEnabled {
    param (
        [string]$Hash,
        [bool]$Enabled
    )
    $path = "$SchannelBase\Hashes\$Hash"
    if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }
    $value = if ($Enabled) { 0xFFFFFFFF } else { 0 }
    Set-ItemProperty -Path $path -Name 'Enabled' -Value $value -Type DWord
    Write-Host "  Hash $Hash : Enabled=$Enabled"
}

function Set-KeyExchangeEnabled {
    param (
        [string]$KE,
        [bool]$Enabled
    )
    $path = "$SchannelBase\KeyExchangeAlgorithms\$KE"
    if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }
    $value = if ($Enabled) { 0xFFFFFFFF } else { 0 }
    Set-ItemProperty -Path $path -Name 'Enabled' -Value $value -Type DWord
    Write-Host "  KeyExchange $KE : Enabled=$Enabled"
}

Write-Host "`n=== VAPT #26/#34 — Schannel TLS Hardening ===" -ForegroundColor Cyan

# ──────────────────────────────────────────────────────────
# 1. Disable legacy / weak SSL/TLS protocol versions
# ──────────────────────────────────────────────────────────
Write-Host "`n[1] Disabling legacy protocols..." -ForegroundColor Yellow
Set-SchannelProtocol -Protocol 'SSL 2.0'  -ServerEnabled $false -ClientEnabled $false
Set-SchannelProtocol -Protocol 'SSL 3.0'  -ServerEnabled $false -ClientEnabled $false
Set-SchannelProtocol -Protocol 'TLS 1.0'  -ServerEnabled $false -ClientEnabled $false
Set-SchannelProtocol -Protocol 'TLS 1.1'  -ServerEnabled $false -ClientEnabled $false

# ──────────────────────────────────────────────────────────
# 2. Enable TLS 1.2 and TLS 1.3
# ──────────────────────────────────────────────────────────
Write-Host "`n[2] Enabling TLS 1.2 and TLS 1.3..." -ForegroundColor Yellow
Set-SchannelProtocol -Protocol 'TLS 1.2'  -ServerEnabled $true  -ClientEnabled $true
Set-SchannelProtocol -Protocol 'TLS 1.3'  -ServerEnabled $true  -ClientEnabled $true

# ──────────────────────────────────────────────────────────
# 3. Disable weak cipher suites
# ──────────────────────────────────────────────────────────
Write-Host "`n[3] Disabling weak ciphers..." -ForegroundColor Yellow
$weakCiphers = @(
    'NULL',
    'RC2 40/128',
    'RC2 56/128',
    'RC2 128/128',
    'RC4 40/128',
    'RC4 56/128',
    'RC4 64/128',
    'RC4 128/128',
    'DES 56/56',
    'Triple DES 168'
)
foreach ($cipher in $weakCiphers) { Set-CipherEnabled -Cipher $cipher -Enabled $false }

# ──────────────────────────────────────────────────────────
# 4. Enable strong ciphers
# ──────────────────────────────────────────────────────────
Write-Host "`n[4] Enabling strong ciphers..." -ForegroundColor Yellow
$strongCiphers = @(
    'AES 128/128',
    'AES 256/256'
)
foreach ($cipher in $strongCiphers) { Set-CipherEnabled -Cipher $cipher -Enabled $true }

# ──────────────────────────────────────────────────────────
# 5. Disable weak hashes
# ──────────────────────────────────────────────────────────
Write-Host "`n[5] Configuring hashes..." -ForegroundColor Yellow
Set-HashEnabled -Hash 'MD5'   -Enabled $false
Set-HashEnabled -Hash 'SHA'   -Enabled $false   # SHA-1
Set-HashEnabled -Hash 'SHA256' -Enabled $true
Set-HashEnabled -Hash 'SHA384' -Enabled $true
Set-HashEnabled -Hash 'SHA512' -Enabled $true

# ──────────────────────────────────────────────────────────
# 6. Disable anonymous/weak key exchange; enable ECDH/Diffie-Hellman
# ──────────────────────────────────────────────────────────
Write-Host "`n[6] Configuring key exchange algorithms..." -ForegroundColor Yellow
Set-KeyExchangeEnabled -KE 'PKCS'  -Enabled $false
Set-KeyExchangeEnabled -KE 'Diffie-Hellman'    -Enabled $true
Set-KeyExchangeEnabled -KE 'ECDH'              -Enabled $true

# ──────────────────────────────────────────────────────────
# 7. Set cipher-suite priority (TLS 1.2 ECDHE-AES-GCM suites first)
#    ECDHE provides Perfect Forward Secrecy (PFS).
# ──────────────────────────────────────────────────────────
Write-Host "`n[7] Setting cipher suite priority order..." -ForegroundColor Yellow

$cipherSuites = @(
    # TLS 1.3 (handled automatically by Windows; listed for documentation)
    # 'TLS_AES_256_GCM_SHA384',
    # 'TLS_AES_128_GCM_SHA256',
    # 'TLS_CHACHA20_POLY1305_SHA256',

    # TLS 1.2 — ECDHE + AES-GCM (PFS, AEAD)
    'TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384',
    'TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256',
    'TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384',
    'TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256',

    # TLS 1.2 — DHE + AES-GCM (PFS, AEAD) — fallback when ECDHE unavailable
    'TLS_DHE_RSA_WITH_AES_256_GCM_SHA384',
    'TLS_DHE_RSA_WITH_AES_128_GCM_SHA256'
)

$sslPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Cryptography\Configuration\SSL\00010002'
if (-not (Test-Path $sslPath)) { New-Item -Path $sslPath -Force | Out-Null }
Set-ItemProperty -Path $sslPath -Name 'Functions' -Value ($cipherSuites -join ',') -Type String
Write-Host "  Cipher suite priority list applied."

# ──────────────────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────────────────
Write-Host "`n=== Schannel hardening complete ===" -ForegroundColor Green
Write-Host "IMPORTANT: Restart IIS and/or reboot the server for changes to take effect." -ForegroundColor Red
Write-Host "Verify with: testssl.sh <host> or Qualys SSL Labs (https://www.ssllabs.com/ssltest/)" -ForegroundColor Cyan
