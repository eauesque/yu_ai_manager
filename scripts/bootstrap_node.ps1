# Download a project-scoped Node.js distribution into ./bin/node/.
#
# Called from start.bat when neither a system `node` nor `bin\node\node.exe`
# is found AND the user has consented to the auto-install. The Windows zip
# extracts to node-<version>-win-<arch>\ which we rename to bin\node\ so
# bin\node\node.exe and bin\node\npm.cmd line up with the layout start.bat
# adds to PATH.
#
# Source: https://nodejs.org/dist/<version>/node-<version>-win-<arch>.zip
# Version is pinned (not "latest") so corepack/pnpm versions stay deterministic.

$ErrorActionPreference = "Stop"

$DefaultNodeVersion = "v22.11.0"
$NodeVersion = if ($env:NODE_VERSION) { $env:NODE_VERSION } else { $DefaultNodeVersion }

# Project root = parent of this script's parent (scripts/.. -> project)
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BinDir  = Join-Path $ProjectRoot "bin"
$NodeDir = Join-Path $BinDir "node"
$NodeExe = Join-Path $NodeDir "node.exe"

if (Test-Path $NodeExe) {
    Write-Host "[OK] Node.js already present at $NodeExe"
    & $NodeExe --version
    exit 0
}

$arch = switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { "x64" }
    "ARM64" { "arm64" }
    "x86"   { "x86" }
    default { "x64" }
}

$archiveName = "node-$NodeVersion-win-$arch"
$archive = "$archiveName.zip"
$url = "https://nodejs.org/dist/$NodeVersion/$archive"

Write-Host "[INFO] Downloading Node.js $NodeVersion (win-$arch) from $url"

if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir | Out-Null
}

$tmpZip    = Join-Path $env:TEMP ("node-bootstrap-" + [Guid]::NewGuid().ToString() + ".zip")
$tmpExtract = Join-Path $env:TEMP ("node-bootstrap-" + [Guid]::NewGuid().ToString())
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $tmpZip -UseBasicParsing

    New-Item -ItemType Directory -Path $tmpExtract | Out-Null
    Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force

    $innerDir = Join-Path $tmpExtract $archiveName
    if (-not (Test-Path $innerDir)) {
        Write-Error "Unexpected archive layout (expected $archiveName\)"
        exit 1
    }

    # Replace any partial install (clean slate).
    if (Test-Path $NodeDir) {
        Remove-Item -Path $NodeDir -Recurse -Force
    }
    Move-Item -Path $innerDir -Destination $NodeDir
} finally {
    if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue }
    if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue }
}

if (-not (Test-Path $NodeExe)) {
    Write-Error "node.exe was not produced by the archive at $url"
    exit 1
}

Write-Host "[OK] Node.js installed: $NodeExe"
& $NodeExe --version

# Enable corepack so `pnpm` becomes available without a separate install.
# corepack ships with Node 16+. Failures here are non-fatal.
$Corepack = Join-Path $NodeDir "corepack.cmd"
if (Test-Path $Corepack) {
    try {
        & $Corepack enable pnpm 2>&1 | Out-Null
        Write-Host "[OK] corepack enabled pnpm"
    } catch {
        Write-Host "[WARN] corepack enable pnpm failed (npm fallback will be used)"
    }
}
