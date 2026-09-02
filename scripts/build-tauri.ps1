# ==========================================
# YU AI Manager - Tauri Build Script (PowerShell)
# ==========================================
# Usage:
#   .\scripts\build-tauri.ps1            # Release build
#   .\scripts\build-tauri.ps1 dev        # Dev mode (hot reload)
#   .\scripts\build-tauri.ps1 check      # Prerequisites check only
# ==========================================

param(
    [Parameter(Position = 0)]
    [ValidateSet("build", "dev", "check", "bundle", "clean", "")]
    [string]$Command = "build",
    [Parameter(Position = 1)]
    [switch]$Deep
)

$ErrorActionPreference = "Continue"

# --- Locale detection ---
$_Lang = if ($env:LANG) {
    $l = $env:LANG.Substring(0, [Math]::Min(2, $env:LANG.Length))
    switch ($l) { "ja" { "ja" } "ko" { "ko" } "zh" {
        if ($env:LANG -match "TW|HK") { "zh_TW" } else { "zh_CN" }
    } default { "en" } }
} else {
    $culture = (Get-UICulture).TwoLetterISOLanguageName
    switch ($culture) { "ja" { "ja" } "ko" { "ko" } "zh" {
        if ((Get-UICulture).Name -match "TW|HK") { "zh_TW" } else { "zh_CN" }
    } default { "en" } }
}

# --- Message table ---
$Msg = @{
    "checking_rust" = @{
        ja="Rust toolchain を確認中..."
        en="Checking Rust toolchain..."
        ko="Rust 툴체인 확인 중..."
        zh_TW="正在檢查 Rust 工具鏈..."
        zh_CN="正在检查 Rust 工具链..."
    }
    "err_no_cargo" = @{
        ja="cargo が見つかりません。https://rustup.rs/ からインストールしてください"
        en="cargo not found. Install from https://rustup.rs/"
        ko="cargo를 찾을 수 없습니다. https://rustup.rs/ 에서 설치하세요"
        zh_TW="找不到 cargo。請從 https://rustup.rs/ 安裝"
        zh_CN="找不到 cargo。请从 https://rustup.rs/ 安装"
    }
    "checking_tauri" = @{
        ja="tauri-cli を確認中..."
        en="Checking tauri-cli..."
        ko="tauri-cli 확인 중..."
        zh_TW="正在檢查 tauri-cli..."
        zh_CN="正在检查 tauri-cli..."
    }
    "warn_no_tauri" = @{
        ja="tauri-cli が見つかりません。インストール: cargo install tauri-cli"
        en="tauri-cli not found. Install: cargo install tauri-cli"
        ko="tauri-cli를 찾을 수 없습니다. 설치: cargo install tauri-cli"
        zh_TW="找不到 tauri-cli。安裝: cargo install tauri-cli"
        zh_CN="找不到 tauri-cli。安装: cargo install tauri-cli"
    }
    "skip_no_cargo" = @{
        ja="cargo がないためスキップ"
        en="Skipping (cargo not available)"
        ko="cargo가 없으므로 건너뜀"
        zh_TW="因無 cargo 而跳過"
        zh_CN="因无 cargo 而跳过"
    }
    "checking_pnpm" = @{
        ja="pnpm を確認中..."
        en="Checking pnpm..."
        ko="pnpm 확인 중..."
        zh_TW="正在檢查 pnpm..."
        zh_CN="正在检查 pnpm..."
    }
    "warn_no_pnpm" = @{
        ja="pnpm が見つかりません。npm でフォールバック可能ですが pnpm を推奨します"
        en="pnpm not found. npm fallback available but pnpm is recommended"
        ko="pnpm을 찾을 수 없습니다. npm 폴백이 가능하지만 pnpm을 권장합니다"
        zh_TW="找不到 pnpm。可使用 npm 作為備案，但建議使用 pnpm"
        zh_CN="找不到 pnpm。可使用 npm 作为备选，但建议使用 pnpm"
    }
    "npm_fallback" = @{
        ja="(フォールバック)"
        en="(fallback)"
        ko="(폴백)"
        zh_TW="(備案)"
        zh_CN="(备选)"
    }
    "err_no_node" = @{
        ja="pnpm も npm も見つかりません。Node.js をインストールしてください"
        en="Neither pnpm nor npm found. Please install Node.js"
        ko="pnpm과 npm 모두 찾을 수 없습니다. Node.js를 설치하세요"
        zh_TW="找不到 pnpm 和 npm。請安裝 Node.js"
        zh_CN="找不到 pnpm 和 npm。请安装 Node.js"
    }
    "checking_python" = @{
        ja="Python 環境 (uv / venv) を確認中..."
        en="Checking Python environment (uv / venv)..."
        ko="Python 환경 (uv / venv) 확인 중..."
        zh_TW="正在檢查 Python 環境 (uv / venv)..."
        zh_CN="正在检查 Python 环境 (uv / venv)..."
    }
    "warn_no_python" = @{
        ja="uv も venv も見つかりません。uv sync か python -m venv venv を実行してください"
        en="Neither uv nor venv found. Run 'uv sync' or 'python -m venv venv'"
        ko="uv와 venv 모두 찾을 수 없습니다. 'uv sync' 또는 'python -m venv venv'를 실행하세요"
        zh_TW="找不到 uv 或 venv。請執行 'uv sync' 或 'python -m venv venv'"
        zh_CN="找不到 uv 或 venv。请执行 'uv sync' 或 'python -m venv venv'"
    }
    "uv_fallback_venv" = @{
        ja="(venv フォールバック)"
        en="(venv fallback)"
        ko="(venv 폴백)"
        zh_TW="(venv 備援)"
        zh_CN="(venv 备选)"
    }
    "checking_src_tauri" = @{
        ja="src-tauri/ を確認中..."
        en="Checking src-tauri/..."
        ko="src-tauri/ 확인 중..."
        zh_TW="正在檢查 src-tauri/..."
        zh_CN="正在检查 src-tauri/..."
    }
    "found_cargo_toml" = @{
        ja="src-tauri/Cargo.toml 検出"
        en="src-tauri/Cargo.toml found"
        ko="src-tauri/Cargo.toml 감지됨"
        zh_TW="偵測到 src-tauri/Cargo.toml"
        zh_CN="检测到 src-tauri/Cargo.toml"
    }
    "err_no_cargo_toml" = @{
        ja="src-tauri/Cargo.toml が見つかりません。プロジェクトルートから実行してください"
        en="src-tauri/Cargo.toml not found. Run from the project root"
        ko="src-tauri/Cargo.toml을 찾을 수 없습니다. 프로젝트 루트에서 실행하세요"
        zh_TW="找不到 src-tauri/Cargo.toml。請從專案根目錄執行"
        zh_CN="找不到 src-tauri/Cargo.toml。请从项目根目录执行"
    }
    "checking_webui" = @{
        ja="web_ui.py を確認中..."
        en="Checking web_ui.py..."
        ko="web_ui.py 확인 중..."
        zh_TW="正在檢查 web_ui.py..."
        zh_CN="正在检查 web_ui.py..."
    }
    "found_webui" = @{
        ja="web_ui.py 検出"
        en="web_ui.py found"
        ko="web_ui.py 감지됨"
        zh_TW="偵測到 web_ui.py"
        zh_CN="检测到 web_ui.py"
    }
    "err_no_webui" = @{
        ja="web_ui.py が見つかりません"
        en="web_ui.py not found"
        ko="web_ui.py를 찾을 수 없습니다"
        zh_TW="找不到 web_ui.py"
        zh_CN="找不到 web_ui.py"
    }
    "building_frontend" = @{
        ja="TypeScript フロントエンドをビルド中..."
        en="Building TypeScript frontend..."
        ko="TypeScript 프론트엔드 빌드 중..."
        zh_TW="正在建置 TypeScript 前端..."
        zh_CN="正在构建 TypeScript 前端..."
    }
    "err_frontend_failed" = @{
        ja="フロントエンドのビルドに失敗しました"
        en="Frontend build failed"
        ko="프론트엔드 빌드에 실패했습니다"
        zh_TW="前端建置失敗"
        zh_CN="前端构建失败"
    }
    "frontend_done" = @{
        ja="フロントエンドビルド完了"
        en="Frontend build complete"
        ko="프론트엔드 빌드 완료"
        zh_TW="前端建置完成"
        zh_CN="前端构建完成"
    }
    "prereq_check" = @{
        ja="前提条件チェック..."
        en="Checking prerequisites..."
        ko="전제 조건 확인..."
        zh_TW="正在檢查先決條件..."
        zh_CN="正在检查先决条件..."
    }
    "all_prereqs_ok" = @{
        ja="全ての前提条件を満たしています"
        en="All prerequisites satisfied"
        ko="모든 전제 조건이 충족되었습니다"
        zh_TW="所有先決條件皆已滿足"
        zh_CN="所有先决条件均已满足"
    }
    "prereqs_missing" = @{
        ja="一部の前提条件が不足しています"
        en="Some prerequisites are missing"
        ko="일부 전제 조건이 충족되지 않았습니다"
        zh_TW="部分先決條件不足"
        zh_CN="部分先决条件不足"
    }
    "dev_starting" = @{
        ja="開発モードで起動します..."
        en="Starting in development mode..."
        ko="개발 모드로 시작합니다..."
        zh_TW="以開發模式啟動..."
        zh_CN="以开发模式启动..."
    }
    "prereqs_not_met" = @{
        ja="前提条件が不足しています。先に check を実行してください"
        en="Prerequisites not met. Run 'check' first"
        ko="전제 조건이 충족되지 않았습니다. 먼저 check를 실행하세요"
        zh_TW="先決條件不足。請先執行 check"
        zh_CN="先决条件不足。请先执行 check"
    }
    "prereqs_not_met_short" = @{
        ja="前提条件が不足しています"
        en="Prerequisites not met"
        ko="전제 조건이 충족되지 않았습니다"
        zh_TW="先決條件不足"
        zh_CN="先决条件不足"
    }
    "starting_tauri_dev" = @{
        ja="cargo tauri dev を起動中..."
        en="Starting cargo tauri dev..."
        ko="cargo tauri dev 시작 중..."
        zh_TW="正在啟動 cargo tauri dev..."
        zh_CN="正在启动 cargo tauri dev..."
    }
    "flask_auto_start" = @{
        ja="Flask サーバーは Tauri が自動起動します"
        en="Flask server will be auto-started by Tauri"
        ko="Flask 서버는 Tauri가 자동으로 시작합니다"
        zh_TW="Flask 伺服器由 Tauri 自動啟動"
        zh_CN="Flask 服务器由 Tauri 自动启动"
    }
    "exit_hint" = @{
        ja="終了: ウィンドウを閉じるか Ctrl+C"
        en="Exit: close the window or Ctrl+C"
        ko="종료: 창을 닫거나 Ctrl+C"
        zh_TW="結束: 關閉視窗或 Ctrl+C"
        zh_CN="退出: 关闭窗口或 Ctrl+C"
    }
    "release_starting" = @{
        ja="リリースビルドを開始します..."
        en="Starting release build..."
        ko="릴리스 빌드를 시작합니다..."
        zh_TW="開始發行版建置..."
        zh_CN="开始发行版构建..."
    }
    "tauri_build_running" = @{
        ja="cargo tauri build を実行中 (時間がかかります)..."
        en="Running cargo tauri build (this may take a while)..."
        ko="cargo tauri build 실행 중 (시간이 걸립니다)..."
        zh_TW="正在執行 cargo tauri build (需要一些時間)..."
        zh_CN="正在执行 cargo tauri build (需要一些时间)..."
    }
    "err_tauri_build_failed" = @{
        ja="Tauri ビルドに失敗しました"
        en="Tauri build failed"
        ko="Tauri 빌드에 실패했습니다"
        zh_TW="Tauri 建置失敗"
        zh_CN="Tauri 构建失败"
    }
    "build_done" = @{
        ja="ビルド完了!"
        en="Build complete!"
        ko="빌드 완료!"
        zh_TW="建置完成!"
        zh_CN="构建完成!"
    }
    "artifacts" = @{
        ja="成果物:"
        en="Artifacts:"
        ko="결과물:"
        zh_TW="產出物:"
        zh_CN="产出物:"
    }
}
function Get-Msg($key) { if ($Msg[$key][$_Lang]) { $Msg[$key][$_Lang] } else { $Msg[$key]["en"] } }

# --- Colored helper functions ---
function Write-Info  { param([string]$M) Write-Host "[INFO] " -ForegroundColor Cyan -NoNewline; Write-Host $M }
function Write-Ok    { param([string]$M) Write-Host "[OK]   " -ForegroundColor Green -NoNewline; Write-Host $M }
function Write-Warn  { param([string]$M) Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline; Write-Host $M }
function Write-Err   { param([string]$M) Write-Host "[ERROR]" -ForegroundColor Red -NoNewline; Write-Host " $M" }

# --- Move to project root ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# --- Prerequisites check ---
function Test-Prerequisites {
    $allOk = $true

    # Rust / cargo
    Write-Info (Get-Msg "checking_rust")
    $hasCargo = $false
    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        $rustVer = & rustc --version 2>&1
        Write-Ok "rustc: $rustVer"
        $hasCargo = $true
    } else {
        Write-Err (Get-Msg "err_no_cargo")
        $allOk = $false
    }

    # tauri-cli (only check if cargo exists)
    Write-Info (Get-Msg "checking_tauri")
    if ($hasCargo) {
        $tauriHelp = & cargo tauri --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "tauri-cli: $tauriHelp"
        } else {
            Write-Warn (Get-Msg "warn_no_tauri")
            $allOk = $false
        }
    } else {
        Write-Warn (Get-Msg "skip_no_cargo")
        $allOk = $false
    }

    # pnpm
    Write-Info (Get-Msg "checking_pnpm")
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        $pnpmVer = & pnpm --version 2>&1
        Write-Ok "pnpm: v$pnpmVer"
    } else {
        Write-Warn (Get-Msg "warn_no_pnpm")
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            $fb = Get-Msg "npm_fallback"
            Write-Ok "npm: $(& npm --version 2>&1) $fb"
        } else {
            Write-Err (Get-Msg "err_no_node")
            $allOk = $false
        }
    }

    # Python environment: prefer uv, fallback to venv
    Write-Info (Get-Msg "checking_python")
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $uvVer = & uv --version 2>&1
        $pyVer = & uv run --no-sync python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "uv: $uvVer / Python: $pyVer"
        } else {
            Write-Ok "uv: $uvVer"
        }
    } else {
        $venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
        }
        if (Test-Path $venvPython) {
            $pyVer = & $venvPython --version 2>&1
            $fb = Get-Msg "uv_fallback_venv"
            Write-Ok "Python: $pyVer $fb"
        } else {
            Write-Err (Get-Msg "warn_no_python")
            $allOk = $false
        }
    }

    # src-tauri directory
    Write-Info (Get-Msg "checking_src_tauri")
    if (Test-Path (Join-Path $ProjectRoot "src-tauri\Cargo.toml")) {
        Write-Ok (Get-Msg "found_cargo_toml")
    } else {
        Write-Err (Get-Msg "err_no_cargo_toml")
        $allOk = $false
    }

    # web_ui.py
    Write-Info (Get-Msg "checking_webui")
    if (Test-Path (Join-Path $ProjectRoot "web_ui.py")) {
        Write-Ok (Get-Msg "found_webui")
    } else {
        Write-Err (Get-Msg "err_no_webui")
        $allOk = $false
    }

    return $allOk
}

# --- TypeScript frontend build ---
function Build-Frontend {
    Write-Info (Get-Msg "building_frontend")
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        & pnpm run build
    } else {
        & npm run build
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err (Get-Msg "err_frontend_failed")
        exit 1
    }
    Write-Ok (Get-Msg "frontend_done")
}

# --- Show built artifacts ---
function Show-Artifacts {
    $releaseDir = Join-Path $ProjectRoot "src-tauri\target\release"
    if (-not (Test-Path $releaseDir)) { return }

    Write-Info (Get-Msg "artifacts")
    $found = $false

    # Tauri 2 layout: target/release/{nsis,msi,wix}/*.exe|*.msi
    # Tauri 1 layout: target/release/bundle/{nsis,msi,deb,appimage,dmg}/...
    $candidates = @(
        @{Path = (Join-Path $releaseDir "nsis");           Pattern = "*.exe";      Label = "NSIS"},
        @{Path = (Join-Path $releaseDir "msi");            Pattern = "*.msi";      Label = "MSI" },
        @{Path = (Join-Path $releaseDir "wix");            Pattern = "*.msi";      Label = "WiX" },
        @{Path = (Join-Path $releaseDir "bundle\nsis");    Pattern = "*.exe";      Label = "NSIS"},
        @{Path = (Join-Path $releaseDir "bundle\msi");     Pattern = "*.msi";      Label = "MSI" },
        @{Path = (Join-Path $releaseDir "bundle\deb");     Pattern = "*.deb";      Label = "DEB" },
        @{Path = (Join-Path $releaseDir "bundle\appimage");Pattern = "*.AppImage"; Label = "AppImage"},
        @{Path = (Join-Path $releaseDir "bundle\dmg");     Pattern = "*.dmg";      Label = "DMG" }
    )
    foreach ($c in $candidates) {
        if (Test-Path $c.Path) {
            Get-ChildItem $c.Path -Filter $c.Pattern -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                $sizeMB = [math]::Round($_.Length / 1MB, 1)
                Write-Host "  $($c.Label): $($_.FullName) ($sizeMB MB)" -ForegroundColor Green
                $found = $true
            }
        }
    }

    $exePath = Join-Path $releaseDir "yu-ai-manager.exe"
    if (Test-Path $exePath) {
        $sizeMB = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
        Write-Host "  EXE:  $exePath ($sizeMB MB)" -ForegroundColor Green
        $found = $true
    }
    if (-not $found) {
        Write-Warn "(no installer artifacts found under $releaseDir)"
    }
}

# --- Clean build artifacts ---
function Invoke-Clean {
    param([bool]$DeepClean = $false)

    $targets = @(
        (Join-Path $ProjectRoot "src-tauri\bundle"),
        (Join-Path $ProjectRoot "src-tauri\bundle.zip"),
        (Join-Path $ProjectRoot "src-tauri\target\release\bundle"),
        (Join-Path $ProjectRoot "src-tauri\target\release\nsis"),
        (Join-Path $ProjectRoot "src-tauri\target\release\msi"),
        (Join-Path $ProjectRoot "src-tauri\target\release\wix"),
        (Join-Path $ProjectRoot "src-tauri\target\release\resources")
    )

    foreach ($t in $targets) {
        if (Test-Path $t) {
            Write-Info "Removing $t"
            Remove-Item -Recurse -Force -LiteralPath $t -ErrorAction SilentlyContinue
        }
    }

    if ($DeepClean) {
        Write-Info "Deep clean: cargo clean (removes target/)"
        Set-Location (Join-Path $ProjectRoot "src-tauri")
        & cargo clean
        Set-Location $ProjectRoot
    }

    Write-Ok "Clean complete"
}

# --- Main ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  YU AI Manager - Tauri Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

switch ($Command) {
    "clean" {
        Invoke-Clean -DeepClean:$Deep
    }

    "check" {
        Write-Info (Get-Msg "prereq_check")
        $ok = Test-Prerequisites
        Write-Host ""
        if ($ok) {
            Write-Ok (Get-Msg "all_prereqs_ok")
        } else {
            Write-Err (Get-Msg "prereqs_missing")
            exit 1
        }
    }

    "bundle" {
        # Self-contained build: Python embedded + deps + app files bundled into NSIS installer
        Write-Info "Self-contained bundle build starting..."
        $ok = Test-Prerequisites
        if (-not $ok) {
            Write-Err (Get-Msg "prereqs_not_met")
            exit 1
        }
        Write-Host ""

        Build-Frontend
        Write-Host ""

        # Build yu-server (bundled fast-mode binary): stage_yu_server() in
        # prepare-tauri-bundle.py below hard-fails if this binary is missing.
        Write-Info "Building yu-server (bundled fast-mode binary)..."
        $crateDir = Join-Path $ProjectRoot "crates"
        Push-Location $crateDir
        & cargo build --release -p yu-server
        $yuServerBuildExitCode = $LASTEXITCODE
        Pop-Location
        if ($yuServerBuildExitCode -ne 0) {
            Write-Err "yu-server build failed"
            exit 1
        }
        Write-Host ""

        # Stage bundle: Python + deps + app files into src-tauri/bundle/
        Write-Info "Staging bundle (Python embedded + dependencies + app files)..."
        $prepareScript = Join-Path $ProjectRoot "scripts\prepare-tauri-bundle.py"

        if (Get-Command uv -ErrorAction SilentlyContinue) {
            & uv run python $prepareScript --skip-ts-build
        } else {
            $venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
            if (-not (Test-Path $venvPython)) {
                $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
            }
            if (Test-Path $venvPython) {
                & $venvPython $prepareScript --skip-ts-build
            } else {
                & python $prepareScript --skip-ts-build
            }
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Bundle preparation failed"
            exit 1
        }
        Write-Host ""

        # Run cargo tauri build with bundle resources injected via TAURI_CONFIG
        Write-Info (Get-Msg "tauri_build_running")
        $env:TAURI_CONFIG = '{"bundle":{"resources":{"bundle/**/*":"bundle/"}}}'
        Set-Location (Join-Path $ProjectRoot "src-tauri")
        & cargo tauri build
        $buildResult = $LASTEXITCODE
        $env:TAURI_CONFIG = $null
        Set-Location $ProjectRoot

        if ($buildResult -ne 0) {
            Write-Err (Get-Msg "err_tauri_build_failed")
            exit 1
        }

        Write-Host ""
        Write-Ok (Get-Msg "build_done")
        Write-Host ""
        Show-Artifacts
    }

    "dev" {
        Write-Info (Get-Msg "dev_starting")
        $ok = Test-Prerequisites
        if (-not $ok) {
            Write-Err (Get-Msg "prereqs_not_met")
            exit 1
        }
        Write-Host ""

        Build-Frontend
        Write-Host ""

        Write-Info (Get-Msg "starting_tauri_dev")
        Write-Info (Get-Msg "flask_auto_start")
        Write-Info (Get-Msg "exit_hint")
        Write-Host ""
        Set-Location (Join-Path $ProjectRoot "src-tauri")
        & cargo tauri dev
        Set-Location $ProjectRoot
    }

    default {
        # "build" or ""
        Write-Info (Get-Msg "release_starting")
        $ok = Test-Prerequisites
        if (-not $ok) {
            Write-Err (Get-Msg "prereqs_not_met_short")
            exit 1
        }
        Write-Host ""

        Build-Frontend
        Write-Host ""

        Write-Info (Get-Msg "tauri_build_running")
        Set-Location (Join-Path $ProjectRoot "src-tauri")
        & cargo tauri build
        $buildResult = $LASTEXITCODE
        Set-Location $ProjectRoot

        if ($buildResult -ne 0) {
            Write-Err (Get-Msg "err_tauri_build_failed")
            exit 1
        }

        Write-Host ""
        Write-Ok (Get-Msg "build_done")
        Write-Host ""
        Show-Artifacts
    }
}

Write-Host ""
