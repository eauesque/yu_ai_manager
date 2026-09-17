# Download a project-scoped ffmpeg (release-essentials build) into ./bin/ffmpeg/.
#
# Source: gyan.dev's release-essentials build, which is a stable versioned
# Windows distribution. Pinned to a specific version so behavior across
# environments is reproducible. Override with $env:FFMPEG_VERSION to test newer.
#
# The zip extracts to ffmpeg-<version>-essentials_build\{bin,doc,presets}\.
# We flatten the bin\*.exe out to ./bin/ffmpeg/ so callers only need to add
# that single directory to PATH (matching the macOS layout).

$ErrorActionPreference = "Stop"

# Pin to ffmpeg 7.1 release-essentials. gyan.dev keeps versioned zips at
# https://www.gyan.dev/ffmpeg/builds/packages/ — these URLs are stable.
$DefaultFfmpegVersion = "7.1"
$FfmpegVersion = if ($env:FFMPEG_VERSION) { $env:FFMPEG_VERSION } else { $DefaultFfmpegVersion }

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BinDir    = Join-Path $ProjectRoot "bin"
$FfmpegDir = Join-Path $BinDir "ffmpeg"
$FfmpegExe = Join-Path $FfmpegDir "ffmpeg.exe"

if (Test-Path $FfmpegExe) {
    Write-Host "[OK] ffmpeg already present at $FfmpegExe"
    & $FfmpegExe -version | Select-Object -First 1
    exit 0
}

$archiveName = "ffmpeg-$FfmpegVersion-essentials_build"
$archive = "$archiveName.zip"
$url = "https://www.gyan.dev/ffmpeg/builds/packages/$archive"

Write-Host "[INFO] Downloading ffmpeg $FfmpegVersion (release-essentials, win64) from $url"

if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir | Out-Null
}

$tmpZip     = Join-Path $env:TEMP ("ffmpeg-bootstrap-" + [Guid]::NewGuid().ToString() + ".zip")
$tmpExtract = Join-Path $env:TEMP ("ffmpeg-bootstrap-" + [Guid]::NewGuid().ToString())
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $tmpZip -UseBasicParsing

    New-Item -ItemType Directory -Path $tmpExtract | Out-Null
    Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force

    $innerDir = Join-Path $tmpExtract $archiveName
    if (-not (Test-Path $innerDir)) {
        # Fallback: gyan.dev sometimes ships with a slightly different folder
        # name (e.g., date-tagged). Take the first subdirectory we find.
        $innerDir = (Get-ChildItem $tmpExtract -Directory | Select-Object -First 1).FullName
    }
    if (-not $innerDir -or -not (Test-Path $innerDir)) {
        Write-Error "Unexpected archive layout"
        exit 1
    }

    $binSrc = Join-Path $innerDir "bin"
    if (-not (Test-Path $binSrc)) {
        Write-Error "bin\ subdirectory missing in archive"
        exit 1
    }

    # Replace any partial install (clean slate).
    if (Test-Path $FfmpegDir) {
        Remove-Item -Path $FfmpegDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $FfmpegDir | Out-Null

    # Flatten bin/*.exe (and any companion DLLs) into ./bin/ffmpeg/.
    Get-ChildItem $binSrc -File | ForEach-Object {
        Move-Item -Path $_.FullName -Destination (Join-Path $FfmpegDir $_.Name)
    }
} finally {
    if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue }
    if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue }
}

if (-not (Test-Path $FfmpegExe)) {
    Write-Error "ffmpeg.exe was not produced by the archive at $url"
    exit 1
}

Write-Host "[OK] ffmpeg installed: $FfmpegExe"
& $FfmpegExe -version | Select-Object -First 1
