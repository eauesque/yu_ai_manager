# ==========================================
# YU AI Manager - Rust server release build (PowerShell)
# ==========================================
# Usage:
#   .\scripts\build-rust-server.ps1                         # Release build (DirectML by default)
#   .\scripts\build-rust-server.ps1 -Hailo DIR              # Build with HailoRT
#   .\scripts\build-rust-server.ps1 -OpenSslDir DIR         # Set OPENSSL_DIR explicitly
#   .\scripts\build-rust-server.ps1 -GpuFeature cuda        # Override GPU EP (cuda/rocm/openvino/"")
#   .\scripts\build-rust-server.ps1 -NoStrip                # Skip binary strip
#   .\scripts\build-rust-server.ps1 check                   # Prerequisites check only
#
# Windows prerequisites:
#   Perl (required — openssl-src builds OpenSSL from source):
#     winget install StrawberryPerl.StrawberryPerl  OR  choco install strawberryperl
#   OpenSSL (any one is sufficient):
#   1. choco install openssl  → sets OPENSSL_DIR automatically
#   2. vcpkg install openssl:x64-windows-static-md  (set VCPKG_ROOT)
#   3. .\build-rust-server.ps1 -OpenSslDir "C:\OpenSSL-Win64"
#   4. $env:OPENSSL_DIR = "C:\OpenSSL-Win64"  (set before running)
# ==========================================

param(
    [Parameter(Position = 0)]
    [ValidateSet("build", "check", "")]
    [string]$Command = "build",
    [string]$Hailo = "",
    [string]$OpenSslDir = "",
    [string]$GpuFeature = "directml",
    [switch]$NoStrip
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$CratesDir   = Join-Path $ProjectRoot "crates"

function Write-Info  { param($m) Write-Host "[INFO] $m" -ForegroundColor Cyan    }
function Write-Ok    { param($m) Write-Host "[OK]   $m" -ForegroundColor Green   }
function Write-Warn  { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow  }
function Write-Err   { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

# ── locale ────────────────────────────────────────────────────────────────────
$_Lang = if ($env:LANG) {
    $l = $env:LANG.Substring(0, [Math]::Min(2, $env:LANG.Length))
    switch ($l) {
        "ja" { "ja" } "ko" { "ko" }
        "zh" { if ($env:LANG -match "TW|HK") { "zh_TW" } else { "zh_CN" } }
        default { "en" }
    }
} else {
    $culture = (Get-UICulture).TwoLetterISOLanguageName
    switch ($culture) {
        "ja" { "ja" } "ko" { "ko" }
        "zh" { if ((Get-UICulture).Name -match "TW|HK") { "zh_TW" } else { "zh_CN" } }
        default { "en" }
    }
}

# ── i18n ─────────────────────────────────────────────────────────────────────
$Msg = @{
    check_cargo    = @{ ja="cargo を確認中...";        ko="cargo 확인 중...";        zh_TW="正在確認 cargo...";        zh_CN="正在确认 cargo...";        en="Checking cargo..." }
    no_cargo       = @{ ja="cargo が見つかりません — https://rustup.rs/ からインストール"; ko="cargo를 찾을 수 없습니다 — https://rustup.rs/ 설치"; zh_TW="找不到 cargo — 請從 https://rustup.rs/ 安裝"; zh_CN="找不到 cargo — 请从 https://rustup.rs/ 安装"; en="cargo not found — install from https://rustup.rs/" }
    check_openssl  = @{ ja="OpenSSL を確認中...";      ko="OpenSSL 확인 중...";      zh_TW="正在確認 OpenSSL...";      zh_CN="正在确认 OpenSSL...";      en="Checking OpenSSL..." }
    no_openssl     = @{ ja="OpenSSL が見つかりません（警告のみ — ビルドは続行）"; ko="OpenSSL를 찾을 수 없습니다 (경고만 — 빌드 계속)"; zh_TW="找不到 OpenSSL（僅警告 — 繼續編譯）"; zh_CN="找不到 OpenSSL（仅警告 — 继续编译）"; en="OpenSSL not found (warning only — build will proceed)" }
    openssl_hint   = @{ ja="  解決策: choco install openssl / vcpkg install openssl:x64-windows-static-md / -OpenSslDir <dir>"; ko="  해결책: choco install openssl / vcpkg install openssl:x64-windows-static-md / -OpenSslDir <dir>"; zh_TW="  解決方案: choco install openssl / vcpkg install openssl:x64-windows-static-md / -OpenSslDir <dir>"; zh_CN="  解决方案: choco install openssl / vcpkg install openssl:x64-windows-static-md / -OpenSslDir <dir>"; en="  Fix: choco install openssl  OR  vcpkg install openssl:x64-windows-static-md  OR  -OpenSslDir <dir>" }
    check_hailo    = @{ ja="HailoRT ヘッダーを確認中..."; ko="HailoRT 헤더 확인 중..."; zh_TW="正在確認 HailoRT 標頭..."; zh_CN="正在确认 HailoRT 头文件..."; en="Checking HailoRT headers..." }
    no_hailo       = @{ ja="hailo/hailort.hpp が見つかりません"; ko="hailo/hailort.hpp를 찾을 수 없습니다"; zh_TW="找不到 hailo/hailort.hpp"; zh_CN="找不到 hailo/hailort.hpp"; en="hailo/hailort.hpp not found under specified dir" }
    hailo_auto     = @{ ja="HAILO_INCLUDE_DIR 未指定 — build.rs が自動検出（未検出時 stub）"; ko="HAILO_INCLUDE_DIR 미설정 — build.rs 자동 감지 (미검출 시 stub)"; zh_TW="未設定 HAILO_INCLUDE_DIR — build.rs 將自動偵測（未找到時 stub）"; zh_CN="未设置 HAILO_INCLUDE_DIR — build.rs 将自动检测（未找到时 stub）"; en="HAILO_INCLUDE_DIR not set — build.rs will auto-detect (stub if absent)" }
    building       = @{ ja="yu-server をリリースビルド中..."; ko="yu-server 릴리스 빌드 중..."; zh_TW="正在編譯 yu-server（release）..."; zh_CN="正在编译 yu-server（release）..."; en="Building yu-server (release)..." }
    stripped       = @{ ja="バイナリを strip しました"; ko="바이너리 strip 완료"; zh_TW="已 strip 二進位檔"; zh_CN="已 strip 二进制文件"; en="Binary stripped" }
    build_done     = @{ ja="ビルド完了:"; ko="빌드 완료:"; zh_TW="編譯完成:"; zh_CN="编译完成:"; en="Build complete:" }
    prereqs_ok     = @{ ja="全ての前提条件を満たしています"; ko="모든 필수 조건을 충족합니다"; zh_TW="所有前置條件均已滿足"; zh_CN="所有前置条件均已满足"; en="All prerequisites satisfied" }
    check_perl     = @{ ja="Perl を確認中...";             ko="Perl 확인 중...";             zh_TW="正在確認 Perl...";             zh_CN="正在确认 Perl...";             en="Checking Perl..." }
    no_perl        = @{ ja="Perl が見つかりません（openssl-src のビルドに必須）"; ko="Perl을 찾을 수 없습니다 (openssl-src 빌드에 필수)"; zh_TW="找不到 Perl（openssl-src 編譯必要）"; zh_CN="找不到 Perl（openssl-src 编译必要）"; en="Perl not found (required to build openssl-src)" }
    perl_hint      = @{ ja="  解決策: winget install StrawberryPerl.StrawberryPerl  または  choco install strawberryperl  —  インストール後にターミナルを再起動"; ko="  해결책: winget install StrawberryPerl.StrawberryPerl  또는  choco install strawberryperl  —  설치 후 터미널 재시작"; zh_TW="  解決方案: winget install StrawberryPerl.StrawberryPerl  或  choco install strawberryperl  — 安裝後重啟終端"; zh_CN="  解决方案: winget install StrawberryPerl.StrawberryPerl  或  choco install strawberryperl  — 安装后重启终端"; en="  Fix: winget install StrawberryPerl.StrawberryPerl  OR  choco install strawberryperl  — restart terminal after install" }
    prereqs_missing= @{ ja="一部の前提条件が不足しています"; ko="일부 필수 조건이 누락되었습니다"; zh_TW="部分前置條件缺失"; zh_CN="部分前置条件缺失"; en="Some prerequisites missing" }
    prereq_fail    = @{ ja="前提条件を満たしていません — 先に check を実行してください"; ko="필수 조건 미충족 — 먼저 check를 실행하세요"; zh_TW="前置條件不滿足 — 請先執行 check"; zh_CN="前置条件不满足 — 请先执行 check"; en="Prerequisites not met — run: .\build-rust-server.ps1 check" }
    binary_missing = @{ ja="ビルド成功しましたがバイナリが見つかりません"; ko="빌드 성공했지만 바이너리를 찾을 수 없습니다"; zh_TW="編譯成功但找不到二進位檔"; zh_CN="编译成功但找不到二进制文件"; en="Build succeeded but binary not found" }
}

function T { param($key) $m = $Msg[$key]; if ($m.ContainsKey($_Lang)) { $m[$_Lang] } else { $m["en"] } }

# ── prerequisites ─────────────────────────────────────────────────────────────
# Returns $true only if cargo (hard requirement) is present.
# OpenSSL absence is warning-only — openssl-sys has its own detection logic.
function Check-Prereqs {
    $cargoOk = $true

    Write-Info (T "check_cargo")
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        Write-Warn (T "no_cargo"); $cargoOk = $false
    } else {
        Write-Ok "cargo $(cargo --version 2>$null)"
    }

    # Perl is required by openssl-src (bundled-sqlcipher-vendored-openssl feature)
    Write-Info (T "check_perl")
    $perlOk = $false
    if (Get-Command perl -ErrorAction SilentlyContinue) {
        $pv = perl -e 'print $^V' 2>$null
        if ($LASTEXITCODE -eq 0 -and $pv) {
            Write-Ok "perl $pv"
            $perlOk = $true
        }
        # If exit code non-zero or empty output, fall through to Strawberry path check
    }
    if (-not $perlOk) {
        # Check Strawberry Perl common install locations and add to PATH
        foreach ($p in @("C:\Strawberry\perl\bin\perl.exe", "C:\strawberry\perl\bin\perl.exe")) {
            if (Test-Path $p) {
                $env:PATH = "$(Split-Path $p);$env:PATH"
                $pv2 = & $p -e 'print $^V' 2>$null
                if ($LASTEXITCODE -eq 0 -and $pv2) {
                    Write-Ok "perl $pv2 (Strawberry at $p)"
                    $perlOk = $true
                    break
                }
            }
        }
    }
    if (-not $perlOk) {
        Write-Warn (T "no_perl")
        Write-Warn (T "perl_hint")
        $cargoOk = $false
    }

    Write-Info (T "check_openssl")
    $sslFound = $false
    # 1. explicit param / env var
    $sslSearchDir = if ($OpenSslDir) { $OpenSslDir } elseif ($env:OPENSSL_DIR) { $env:OPENSSL_DIR } else { "" }
    if ($sslSearchDir) {
        $h = Join-Path $sslSearchDir "include\openssl\ssl.h"
        if (Test-Path $h) { Write-Ok "openssl ($sslSearchDir)"; $sslFound = $true }
    }
    # 2. vcpkg / choco / system paths
    if (-not $sslFound) {
        $candidates = @(
            "$env:VCPKG_ROOT\installed\x64-windows-static-md\include\openssl\ssl.h",
            "$env:VCPKG_ROOT\installed\x64-windows\include\openssl\ssl.h",
            "C:\Program Files\OpenSSL-Win64\include\openssl\ssl.h",
            "C:\OpenSSL-Win64\include\openssl\ssl.h",
            "C:\OpenSSL\include\openssl\ssl.h"
        )
        foreach ($p in $candidates) {
            if ($p -and (Test-Path $p)) { Write-Ok "openssl ($p)"; $sslFound = $true; break }
        }
    }
    # 3. pkg-config (WSL2 / MSYS2)
    if (-not $sslFound -and (Get-Command pkg-config -ErrorAction SilentlyContinue)) {
        $v = pkg-config --modversion openssl 2>$null
        if ($v) { Write-Ok "openssl $v"; $sslFound = $true }
    }
    if (-not $sslFound) {
        Write-Warn (T "no_openssl")
        Write-Warn (T "openssl_hint")
    }

    if ($Hailo) {
        Write-Info "$(T 'check_hailo') ($Hailo)"
        if (-not (Test-Path (Join-Path $Hailo "hailo\hailort.hpp"))) {
            Write-Warn (T "no_hailo")
            # Hard fail only when user explicitly specified a Hailo path that doesn't work
            return $false
        }
        Write-Ok "HailoRT headers found"
    } else {
        Write-Info (T "hailo_auto")
    }

    return $cargoOk
}

if ($Command -eq "check") {
    $r = Check-Prereqs
    if ($r) { Write-Ok (T "prereqs_ok") } else { Write-Warn (T "prereqs_missing"); exit 1 }
    exit 0
}

# ── build ─────────────────────────────────────────────────────────────────────
# Only cargo absence blocks the build; OpenSSL warnings are advisory.
$cargoOk = Check-Prereqs
if (-not $cargoOk) { Write-Err (T "prereq_fail") }

Write-Info (T "building")
Set-Location $CratesDir

if ($Hailo)      { $env:HAILO_INCLUDE_DIR = $Hailo }
if ($OpenSslDir) { $env:OPENSSL_DIR = $OpenSslDir }

$cargoArgs = @("build", "--release", "-p", "yu-server")
if ($GpuFeature) {
    $cargoArgs += @("--features", $GpuFeature)
    Write-Info "GPU EP: $GpuFeature"
}
& cargo @cargoArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Respect CARGO_TARGET_DIR if set
$TargetDir = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { Join-Path $CratesDir "target" }
$Binary = Join-Path $TargetDir "release\yu-server.exe"
# Linux binary name on WSL2
if (-not (Test-Path $Binary)) { $Binary = Join-Path $TargetDir "release\yu-server" }
if (-not (Test-Path $Binary)) { Write-Err "$(T 'binary_missing'): $Binary" }

if (-not $NoStrip -and (Get-Command strip -ErrorAction SilentlyContinue)) {
    strip $Binary
    Write-Ok (T "stripped")
}

$size = (Get-Item $Binary).Length / 1MB
Write-Ok "$(T 'build_done') $Binary ($([math]::Round($size,1)) MB)"
