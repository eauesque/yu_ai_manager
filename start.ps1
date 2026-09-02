# start.ps1 -- YU AI Manager Launcher
# Invoked by start.bat (2-line ASCII stub). PowerShell handles Unicode natively,
# so this file carries all locale-aware messages and launch logic.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$LaunchArgs
)

$ErrorActionPreference = 'Continue'
$scriptDir = $PSScriptRoot

# Console encoding: match the chcp 65001 the caller would have set
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

$host.UI.RawUI.WindowTitle = 'YU AI Manager'
Set-Location $scriptDir
$env:PATH = "$(Join-Path $scriptDir 'bin');$env:PATH"

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $scriptDir 'tmp\.uv-cache'
}

# --- Safe mode ---
$safeMode = $LaunchArgs -contains '--safe-mode'
if ($safeMode) { Write-Host '[SAFE MODE] Passing --safe-mode to web_ui.py' }

# --- Locale detection ---
$lang = $null
if ($env:LANG) {
    $l = $env:LANG
    if     ($l -like 'ja*')    { $lang = 'ja' }
    elseif ($l -like 'ko*')    { $lang = 'ko' }
    elseif ($l -like 'zh_TW*' -or $l -like 'zh_HK*') { $lang = 'zh_TW' }
    elseif ($l -like 'zh_CN*' -or $l -like 'zh_SG*') { $lang = 'zh_CN' }
    elseif ($l -like 'en*')    { $lang = 'en' }
}
if (-not $lang) {
    $uiCult = (Get-UICulture).TwoLetterISOLanguageName
    if     ($uiCult -eq 'ja') { $lang = 'ja' }
    elseif ($uiCult -eq 'ko') { $lang = 'ko' }
    elseif ($uiCult -eq 'zh') {
        $uiFull = (Get-UICulture).Name
        if   ($uiFull -in 'zh-TW','zh-HK') { $lang = 'zh_TW' }
        elseif ($uiFull -in 'zh-CN','zh-SG') { $lang = 'zh_CN' }
        else { $lang = 'zh_CN' }
    }
}
if (-not $lang) { $lang = 'en' }

# --- i18n messages ---
switch ($lang) {
    'ja' {
        $MSG_PORTABLE          = '[PORTABLE] 同梱 Python を使用します'
        $MSG_PYTHON_NOT_FOUND  = '[ERROR] Python が見つかりません。'
        $MSG_PYTHON_INSTALL    = '  以下から Python 3.11 以上をインストールしてください:'
        $MSG_PYTHON_PATH       = '  インストール時に「Add Python to PATH」にチェックを入れてください。'
        $MSG_NODE_NOT_FOUND    = '[INFO] Node.js が見つかりません。'
        $MSG_NODE_NEED         = '  フロントエンドのビルドには Node.js 22 LTS が必要です。'
        $MSG_NODE_PROMPT       = '  ./bin/node/ にダウンロードしますか? (約 30 MB, 管理者権限不要) [Y/n]: '
        $MSG_NODE_OPTIONAL     = '  Node.js がなくてもビルド済みファイルがあれば起動できます。'
        $MSG_NODE_SKIP         = '  スキップしました。続行します...'
        $MSG_NODE_FAIL         = '[WARNING] Node.js の自動インストールに失敗しました。続行します...'
        $MSG_FFMPEG_NOT_FOUND  = '[INFO] ffmpeg が見つかりません。'
        $MSG_FFMPEG_NEED       = '  動画分析・S2T・OCR 等の拡張機能で必要です (本体起動には不要)。'
        $MSG_FFMPEG_PROMPT     = '  ./bin/ffmpeg/ にダウンロードしますか? (約 80 MB, 管理者権限不要) [Y/n]: '
        $MSG_FFMPEG_SKIP       = '  スキップしました。動画系の拡張機能は無効になります。'
        $MSG_FFMPEG_FAIL       = '[WARNING] ffmpeg の自動インストールに失敗しました。続行します...'
        $MSG_ARGS_FOUND        = '[OK] launch-args.txt を検出'
        $MSG_ARGS_NONE         = '[INFO] launch-args.txt なし (デフォルト設定で起動)'
        $MSG_STARTING          = 'サーバーを起動しています...'
        $MSG_STOP_HINT         = 'Ctrl+C で停止できます。'
        $MSG_ERROR             = '[ERROR] サーバーが異常終了しました'
        $MSG_DIST_STALE        = '[INFO] Web UI バンドル (dist) が古いため再ビルドします...'
        $MSG_DIST_BUILD_OK     = '[OK] ビルド完了。サーバーを再起動します...'
        $MSG_DIST_BUILD_FAIL   = '[ERROR] pnpm run build に失敗しました。'
        $MSG_DIST_NO_NODE      = '[ERROR] dist が古いですが Node.js がないため自動ビルドできません。YU_SKIP_DIST_CHECK=1 を付けて起動するとそのまま動かせます。'
    }
    'ko' {
        $MSG_PORTABLE          = '[PORTABLE] 동봉된 Python을 사용합니다'
        $MSG_PYTHON_NOT_FOUND  = '[ERROR] Python을 찾을 수 없습니다.'
        $MSG_PYTHON_INSTALL    = '  아래에서 Python 3.11 이상을 설치하세요:'
        $MSG_PYTHON_PATH       = "  설치 시 'Add Python to PATH'를 체크하세요."
        $MSG_NODE_NOT_FOUND    = '[INFO] Node.js를 찾을 수 없습니다.'
        $MSG_NODE_NEED         = '  프론트엔드 빌드에는 Node.js 22 LTS가 필요합니다.'
        $MSG_NODE_PROMPT       = '  ./bin/node/에 다운로드하시겠습니까? (약 30 MB, 관리자 권한 불필요) [Y/n]: '
        $MSG_NODE_OPTIONAL     = '  Node.js가 없어도 빌드된 파일이 있으면 시작할 수 있습니다.'
        $MSG_NODE_SKIP         = '  건너뛰었습니다. 계속합니다...'
        $MSG_NODE_FAIL         = '[WARNING] Node.js 자동 설치 실패. 계속합니다...'
        $MSG_FFMPEG_NOT_FOUND  = '[INFO] ffmpeg를 찾을 수 없습니다.'
        $MSG_FFMPEG_NEED       = '  동영상 분석/S2T/OCR 등 확장 기능에 필요 (본체 실행에는 불필요).'
        $MSG_FFMPEG_PROMPT     = '  ./bin/ffmpeg/에 다운로드하시겠습니까? (약 80 MB, 관리자 권한 불필요) [Y/n]: '
        $MSG_FFMPEG_SKIP       = '  건너뛰었습니다. 동영상 관련 확장 기능은 비활성화됩니다.'
        $MSG_FFMPEG_FAIL       = '[WARNING] ffmpeg 자동 설치 실패. 계속합니다...'
        $MSG_ARGS_FOUND        = '[OK] launch-args.txt 감지됨'
        $MSG_ARGS_NONE         = '[INFO] launch-args.txt 없음 (기본 설정으로 시작)'
        $MSG_STARTING          = '서버를 시작하는 중...'
        $MSG_STOP_HINT         = 'Ctrl+C로 중지할 수 있습니다.'
        $MSG_ERROR             = '[ERROR] 서버가 비정상 종료되었습니다'
        $MSG_DIST_STALE        = '[INFO] 웹 UI 번들(dist)이 오래되어 재빌드합니다...'
        $MSG_DIST_BUILD_OK     = '[OK] 빌드 완료. 서버를 다시 시작합니다...'
        $MSG_DIST_BUILD_FAIL   = '[ERROR] pnpm run build 실패.'
        $MSG_DIST_NO_NODE      = '[ERROR] dist가 오래되었지만 Node.js가 없어 자동 빌드할 수 없습니다. YU_SKIP_DIST_CHECK=1을 설정하면 그대로 실행할 수 있습니다.'
    }
    'zh_TW' {
        $MSG_PORTABLE          = '[PORTABLE] 使用內建 Python'
        $MSG_PYTHON_NOT_FOUND  = '[ERROR] 找不到 Python。'
        $MSG_PYTHON_INSTALL    = '  請從以下位置安裝 Python 3.11 以上版本：'
        $MSG_PYTHON_PATH       = '  安裝時請勾選「Add Python to PATH」。'
        $MSG_NODE_NOT_FOUND    = '[INFO] 找不到 Node.js。'
        $MSG_NODE_NEED         = '  前端建置需要 Node.js 22 LTS。'
        $MSG_NODE_PROMPT       = '  下載到 ./bin/node/ 嗎? (約 30 MB, 不需管理者權限) [Y/n]: '
        $MSG_NODE_OPTIONAL     = '  沒有 Node.js 也可以使用已建置的檔案啟動。'
        $MSG_NODE_SKIP         = '  已略過。繼續啟動...'
        $MSG_NODE_FAIL         = '[WARNING] Node.js 自動安裝失敗。繼續啟動...'
        $MSG_FFMPEG_NOT_FOUND  = '[INFO] 找不到 ffmpeg。'
        $MSG_FFMPEG_NEED       = '  影片分析/S2T/OCR 等擴充功能需要 (主程式啟動不需要)。'
        $MSG_FFMPEG_PROMPT     = '  下載到 ./bin/ffmpeg/ 嗎? (約 80 MB, 不需管理者權限) [Y/n]: '
        $MSG_FFMPEG_SKIP       = '  已略過。影片相關擴充功能將停用。'
        $MSG_FFMPEG_FAIL       = '[WARNING] ffmpeg 自動安裝失敗。繼續啟動...'
        $MSG_ARGS_FOUND        = '[OK] 偵測到 launch-args.txt'
        $MSG_ARGS_NONE         = '[INFO] 無 launch-args.txt（使用預設設定啟動）'
        $MSG_STARTING          = '正在啟動伺服器...'
        $MSG_STOP_HINT         = '按 Ctrl+C 可停止。'
        $MSG_ERROR             = '[ERROR] 伺服器異常終止'
        $MSG_DIST_STALE        = '[INFO] Web UI bundle (dist) 已過時，正在重新建置...'
        $MSG_DIST_BUILD_OK     = '[OK] 建置完成。正在重新啟動伺服器...'
        $MSG_DIST_BUILD_FAIL   = '[ERROR] pnpm run build 失敗。'
        $MSG_DIST_NO_NODE      = '[ERROR] dist 已過時，但找不到 Node.js 無法自動建置。設定 YU_SKIP_DIST_CHECK=1 可以照樣啟動。'
    }
    'zh_CN' {
        $MSG_PORTABLE          = '[PORTABLE] 使用内置 Python'
        $MSG_PYTHON_NOT_FOUND  = '[ERROR] 找不到 Python。'
        $MSG_PYTHON_INSTALL    = '  请从以下位置安装 Python 3.11 以上版本：'
        $MSG_PYTHON_PATH       = '  安装时请勾选「Add Python to PATH」。'
        $MSG_NODE_NOT_FOUND    = '[INFO] 找不到 Node.js。'
        $MSG_NODE_NEED         = '  前端构建需要 Node.js 22 LTS。'
        $MSG_NODE_PROMPT       = '  下载到 ./bin/node/ 吗? (约 30 MB, 不需管理员权限) [Y/n]: '
        $MSG_NODE_OPTIONAL     = '  没有 Node.js 也可以使用已构建的文件启动。'
        $MSG_NODE_SKIP         = '  已跳过。继续启动...'
        $MSG_NODE_FAIL         = '[WARNING] Node.js 自动安装失败。继续启动...'
        $MSG_FFMPEG_NOT_FOUND  = '[INFO] 找不到 ffmpeg。'
        $MSG_FFMPEG_NEED       = '  视频分析/S2T/OCR 等扩展功能需要 (主程序启动不需要)。'
        $MSG_FFMPEG_PROMPT     = '  下载到 ./bin/ffmpeg/ 吗? (约 80 MB, 不需管理员权限) [Y/n]: '
        $MSG_FFMPEG_SKIP       = '  已跳过。视频相关扩展功能将停用。'
        $MSG_FFMPEG_FAIL       = '[WARNING] ffmpeg 自动安装失败。继续启动...'
        $MSG_ARGS_FOUND        = '[OK] 检测到 launch-args.txt'
        $MSG_ARGS_NONE         = '[INFO] 无 launch-args.txt（使用默认设置启动）'
        $MSG_STARTING          = '正在启动服务器...'
        $MSG_STOP_HINT         = '按 Ctrl+C 可停止。'
        $MSG_ERROR             = '[ERROR] 服务器异常终止'
        $MSG_DIST_STALE        = '[INFO] Web UI bundle (dist) 已过时，正在重新构建...'
        $MSG_DIST_BUILD_OK     = '[OK] 构建完成。正在重启服务器...'
        $MSG_DIST_BUILD_FAIL   = '[ERROR] pnpm run build 失败。'
        $MSG_DIST_NO_NODE      = '[ERROR] dist 已过时，但未找到 Node.js 无法自动构建。设置 YU_SKIP_DIST_CHECK=1 可以照样启动。'
    }
    default {
        $MSG_PORTABLE          = '[PORTABLE] Using bundled Python'
        $MSG_PYTHON_NOT_FOUND  = '[ERROR] Python not found.'
        $MSG_PYTHON_INSTALL    = '  Please install Python 3.11 or later from:'
        $MSG_PYTHON_PATH       = "  Make sure to check 'Add Python to PATH' during installation."
        $MSG_NODE_NOT_FOUND    = '[INFO] Node.js not found.'
        $MSG_NODE_NEED         = '  Node.js 22 LTS is required to build the frontend.'
        $MSG_NODE_PROMPT       = '  Download to ./bin/node/? (~30 MB, no admin needed) [Y/n]: '
        $MSG_NODE_OPTIONAL     = '  You can still start if pre-built files exist.'
        $MSG_NODE_SKIP         = '  Skipped. Continuing...'
        $MSG_NODE_FAIL         = '[WARNING] Node.js auto-install failed. Continuing...'
        $MSG_FFMPEG_NOT_FOUND  = '[INFO] ffmpeg not found.'
        $MSG_FFMPEG_NEED       = '  Required by video/S2T/OCR extensions (the app itself starts without it).'
        $MSG_FFMPEG_PROMPT     = '  Download to ./bin/ffmpeg/? (~80 MB, no admin needed) [Y/n]: '
        $MSG_FFMPEG_SKIP       = '  Skipped. Video-related extensions will be disabled.'
        $MSG_FFMPEG_FAIL       = '[WARNING] ffmpeg auto-install failed. Continuing...'
        $MSG_ARGS_FOUND        = '[OK] launch-args.txt detected'
        $MSG_ARGS_NONE         = '[INFO] No launch-args.txt (using default settings)'
        $MSG_STARTING          = 'Starting server...'
        $MSG_STOP_HINT         = 'Press Ctrl+C to stop.'
        $MSG_ERROR             = '[ERROR] Server terminated abnormally'
        $MSG_DIST_STALE        = '[INFO] Web UI bundle (dist) is out of date - rebuilding...'
        $MSG_DIST_BUILD_OK     = '[OK] Build complete - restarting server...'
        $MSG_DIST_BUILD_FAIL   = '[ERROR] pnpm run build failed.'
        $MSG_DIST_NO_NODE      = '[ERROR] dist is stale but Node.js is not available; cannot auto-build. Set YU_SKIP_DIST_CHECK=1 to start anyway.'
    }
}

Write-Host '============================================'
Write-Host '  YU AI Manager - Launcher'
Write-Host '============================================'
Write-Host ''

# --- Portable mode detection (highest priority -- used by Tauri bundle) ---
$portablePython = Join-Path $scriptDir 'python\python.exe'
$usePortable    = $false
$uvBin          = Join-Path $scriptDir 'bin\uv.exe'
$onnxExtra      = $null

if (Test-Path $portablePython) {
    Write-Host $MSG_PORTABLE
    $pyver = & $portablePython --version 2>&1
    Write-Host "[OK] $pyver"
    $usePortable = $true
}

if (-not $usePortable) {
    # --- uv bootstrap ---
    if (-not (Test-Path $uvBin)) {
        Write-Host '[INFO] uv not found, downloading project-scoped binary...'
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir 'scripts\bootstrap_uv.ps1')
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[ERROR] uv download failed. Check your network connection.'
            Write-Host '        Manual install: https://docs.astral.sh/uv/getting-started/installation/'
            Read-Host 'Press Enter to exit'
            exit 1
        }
    }
    $uvver = & $uvBin --version 2>&1
    Write-Host "[OK] $uvver"

    & $uvBin 'run' '--no-project' '--quiet' 'python' 'scripts\post_restart_apply.py'

    # --- Security audit (non-blocking, throttled to 24h) ---
    if ($safeMode) {
        Write-Host '[SAFE MODE] Security audit skipped'
    } elseif ($env:YU_SKIP_SECURITY_AUDIT -ne '1') {
        $auditMode = if ($env:YU_AUTO_SECURITY_PATCH -eq '1') { 'apply' } else { 'notify' }
        & $uvBin 'run' '--no-project' '--quiet' 'python' 'scripts\security_audit.py' '--mode' $auditMode
    }

    # --- onnxruntime variant selection ---
    $onnxFile = Join-Path $scriptDir '.onnx_extra'
    if ($safeMode) {
        $onnxExtra = 'cpu'
    } elseif (Test-Path $onnxFile) {
        $onnxExtra = (Get-Content $onnxFile -Raw).Trim()
    }
    if (-not $onnxExtra) {
        $onnxExtra = (& $uvBin 'run' '--no-project' '--quiet' 'python' 'scripts\detect_onnx_extra.py' 2>$null)
        if ($onnxExtra) { $onnxExtra = $onnxExtra.Trim() }
        if (-not $onnxExtra) { $onnxExtra = 'cpu' }
        Set-Content $onnxFile $onnxExtra
    }
    Write-Host "[OK] onnxruntime variant: $onnxExtra"
if (-not $safeMode) {
    & $uvBin 'run' '--no-project' '--quiet' 'python' 'scripts\install_onnx.py' '--repair' '--variant' $onnxExtra
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
    # --- Node.js check ---
    $localNodeDir = Join-Path $scriptDir 'bin\node'
    $localNodeExe = Join-Path $localNodeDir 'node.exe'

    $nodeReady = $false
    if (Test-Path $localNodeExe) {
        $env:PATH = "$localNodeDir;$env:PATH"
        $nodever = & $localNodeExe --version 2>&1
        Write-Host "[OK] Node.js $nodever (project-scoped)"
        $nodeReady = $true
    }
    if (-not $nodeReady -and (Get-Command node -ErrorAction SilentlyContinue)) {
        $nodever = & node --version 2>&1
        Write-Host "[OK] Node.js $nodever"
        $nodeReady = $true
    }
    if (-not $nodeReady) {
        if ($safeMode) {
            Write-Host $MSG_NODE_SKIP
            Write-Host $MSG_NODE_OPTIONAL
        } else {
            Write-Host ''
            Write-Host $MSG_NODE_NOT_FOUND
            Write-Host $MSG_NODE_NEED
            Write-Host ''

            $doInstallNode = $false
            if ($env:YU_AUTO_INSTALL_NODE -eq '1' -or $env:YU_AUTO_INSTALL -eq '1') {
                Write-Host '[INFO] YU_AUTO_INSTALL_NODE=1 - auto-installing'
                $doInstallNode = $true
            } else {
                $ans = Read-Host $MSG_NODE_PROMPT
                if ($ans -eq '' -or $ans -match '^[Yy]') { $doInstallNode = $true }
            }
            if ($doInstallNode) {
                & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir 'scripts\bootstrap_node.ps1')
                $bootstrapRC = $LASTEXITCODE
                if ($bootstrapRC -eq 0 -and (Test-Path $localNodeExe)) {
                    $env:PATH = "$localNodeDir;$env:PATH"
                    $nodever = & $localNodeExe --version 2>&1
                    Write-Host "[OK] Node.js $nodever (project-scoped)"
                } else {
                    Write-Host $MSG_NODE_FAIL
                    Write-Host $MSG_NODE_OPTIONAL
                }
            } else {
                Write-Host $MSG_NODE_SKIP
                Write-Host $MSG_NODE_OPTIONAL
            }
            Write-Host ''
        }
    }

    # --- ffmpeg check ---
    $localFfmpegDir = Join-Path $scriptDir 'bin\ffmpeg'
    $localFfmpegExe = Join-Path $localFfmpegDir 'ffmpeg.exe'

    $ffmpegReady = $false
    if (Test-Path $localFfmpegExe) {
        $env:PATH = "$localFfmpegDir;$env:PATH"
        $ffver = (& $localFfmpegExe -version 2>&1 | Select-Object -First 1)
        Write-Host "[OK] $ffver (project-scoped)"
        $ffmpegReady = $true
    }
    if (-not $ffmpegReady -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        $ffver = (& ffmpeg -version 2>&1 | Select-Object -First 1)
        Write-Host "[OK] $ffver"
        $ffmpegReady = $true
    }
    if (-not $ffmpegReady) {
        if ($safeMode) {
            Write-Host $MSG_FFMPEG_SKIP
        } else {
            Write-Host ''
            Write-Host $MSG_FFMPEG_NOT_FOUND
            Write-Host $MSG_FFMPEG_NEED
            Write-Host ''

            $doInstallFfmpeg = $false
            if ($env:YU_AUTO_INSTALL_FFMPEG -eq '1' -or $env:YU_AUTO_INSTALL -eq '1') {
                Write-Host '[INFO] YU_AUTO_INSTALL_FFMPEG=1 - auto-installing'
                $doInstallFfmpeg = $true
            } else {
                $ans = Read-Host $MSG_FFMPEG_PROMPT
                if ($ans -eq '' -or $ans -match '^[Yy]') { $doInstallFfmpeg = $true }
            }
            if ($doInstallFfmpeg) {
                & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir 'scripts\bootstrap_ffmpeg.ps1')
                $bootstrapRC = $LASTEXITCODE
                if ($bootstrapRC -eq 0 -and (Test-Path $localFfmpegExe)) {
                    $env:PATH = "$localFfmpegDir;$env:PATH"
                    $ffver = (& $localFfmpegExe -version 2>&1 | Select-Object -First 1)
                    Write-Host "[OK] $ffver (project-scoped)"
                } else {
                    Write-Host $MSG_FFMPEG_FAIL
                }
            } else {
                Write-Host $MSG_FFMPEG_SKIP
            }
            Write-Host ''
        }
    }
}

# --- launch-args.txt ---
if (Test-Path (Join-Path $scriptDir 'launch-args.txt')) {
    Write-Host $MSG_ARGS_FOUND
} else {
    Write-Host $MSG_ARGS_NONE
}

# --- Fast mode (Rust) ---
# fast_mode.py is the only judge here too. Keep both launchers thin.
#
# fast_mode.py prints one launch argument per line, not a space-joined
# command line: a real install can sit under a path containing spaces
# ("C:\Users\Taro Yamada"), and Invoke-Expression parses its string argument
# as script text -- an unquoted spaced path is misread as a bare command
# name followed by arguments, throwing CommandNotFoundException. Capturing
# external-process stdout into a variable already gives one array element
# per line in PowerShell (a trailing newline just terminates the last line,
# it does not add an extra empty element -- unlike -split on a string), so
# no manual splitting or empty-element filtering is needed; @() just forces
# the array shape even when there is exactly one line.
#
# stderr is left unredirected (not `2>$null`) so decide()'s reason for
# declining fast mode reaches the user, matching start.sh.
$yuFastArgs = @()
# yu:fast-resolve:begin
function Invoke-YuResolveFastMode {
    if ($usePortable -or $env:YU_SKIP_FAST_MODE -eq "1") { return @() }
    $resolved = @(& $uvBin 'run' '--no-project' '--quiet' 'python' 'scripts\fast_mode.py' `
        '--resolve' '--' @LaunchArgs)
    if ($LASTEXITCODE -ne 0) { return @() }
    if ($resolved.Count -gt 0 -and $resolved[0].StartsWith('__YU_FAST_ENV_DB_KEY__=')) {
        $env:YU_DB_KEY = $resolved[0].Substring('__YU_FAST_ENV_DB_KEY__='.Length)
        return @($resolved | Select-Object -Skip 1)
    }
    return $resolved
}
# yu:fast-resolve:end

$yuFastArgs = Invoke-YuResolveFastMode

Write-Host ''
Write-Host $MSG_STARTING
Write-Host $MSG_STOP_HINT
Write-Host ''

# --- Launch loop ---
# web_ui.py exits 75 (EX_TEMPFAIL) when dist/ is out of sync with src/ts/.
# Catch it, run `pnpm run build`, and retry once.
$distRetry = $false

while ($true) {
    if ($yuFastArgs.Count -gt 0) {
        $fastBin = $yuFastArgs[0]
        $fastRest = @()
        if ($yuFastArgs.Count -gt 1) { $fastRest = $yuFastArgs[1..($yuFastArgs.Count - 1)] }
        $yuFastFailed = $false
        try {
            & $fastBin @fastRest
            $rc = $LASTEXITCODE
        } catch {
            # & threw instead of merely setting a nonzero exit code (e.g. the
            # binary path could not be resolved at all) -- this is the
            # fallback of last resort for a fast-mode launch that cannot
            # actually run. Remember the failure so a later dist-retry
            # iteration of this same loop does not try the Rust binary again.
            $yuFastFailed = $true
        }
        if ($yuFastFailed -or $rc -eq 127 -or $rc -eq 126) {
            # 127/126 mirror start.sh: command not found / found but not
            # executable or invalid format. decide() already runs the binary
            # once via _read_compat_info before approving it, so this path is
            # not expected to be reachable in practice, but there is no
            # reason to leave a hole in the fallback net for it.
            Write-Host '[fast-mode] Rust launch failed; falling back to Python.'
            $yuFastArgs = @()
            $yuFastUnusable = $true
            if ($usePortable) {
                & $portablePython 'web_ui.py' @LaunchArgs
            } else {
                & $uvBin 'run' '--extra' $onnxExtra 'python' 'web_ui.py' @LaunchArgs
            }
            $rc = $LASTEXITCODE
        }
    } elseif ($usePortable) {
        & $portablePython 'web_ui.py' @LaunchArgs
        $rc = $LASTEXITCODE
    } else {
        & $uvBin 'run' '--extra' $onnxExtra 'python' 'web_ui.py' @LaunchArgs
        $rc = $LASTEXITCODE
    }

    if ($rc -eq 75) {
        if ($distRetry) {
            Write-Host '[ERROR] dist still stale after rebuild.'
            Read-Host 'Press Enter to exit'
            exit $rc
        }
        $distRetry = $true

        $built = $false
        if (-not (Test-Path 'node_modules\dictionary-en') -and (Get-Command 'pnpm' -ErrorAction SilentlyContinue)) {
            Write-Host '[INFO] node_modules incomplete — running pnpm install...'
            $env:CI = '1'
            & pnpm 'install'
        }
        foreach ($pkgMgr in @('pnpm','npm')) {
            if (Get-Command $pkgMgr -ErrorAction SilentlyContinue) {
                Write-Host $MSG_DIST_STALE
                & $pkgMgr 'run' 'build'
                if ($LASTEXITCODE -ne 0) {
                    Write-Host $MSG_DIST_BUILD_FAIL
                    Read-Host 'Press Enter to exit'
                    exit $rc
                }
                Write-Host $MSG_DIST_BUILD_OK
                $built = $true
                break
            }
        }
        if (-not $built) {
            Write-Host $MSG_DIST_NO_NODE
            Read-Host 'Press Enter to exit'
            exit $rc
        }
        # The dist bundle was the reason fast mode was refused a moment ago
        # (decide() rejects a stale bundle and, because a binary cannot fix
        # that, skips acquisition entirely). Ask again now that it is fresh,
        # or this launch runs Python for no remaining reason and the recorded
        # verdict keeps naming a staleness that has already been fixed. Not
        # after a Rust binary that would not run: re-resolving would hand back
        # the same unusable binary this loop just fell back from.
        if (-not $yuFastUnusable) {
            $yuFastArgs = Invoke-YuResolveFastMode
        }
        continue
    }

    if ($rc -ne 0) {
        Write-Host ''
        Write-Host "$MSG_ERROR (exit code: $rc)"
        Read-Host 'Press Enter to exit'
    }
    break
}
