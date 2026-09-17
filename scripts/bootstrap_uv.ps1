# Download a project-scoped uv binary into ./bin/uv.exe.
#
# Called from start.bat when bin\uv.exe is missing. Idempotent: if the binary
# already exists this script is a no-op (start.bat skips invocation entirely).
#
# Source: https://github.com/astral-sh/uv/releases/download/<UV_VERSION>/uv-<triple>.zip
# The Windows zip flattens to uv.exe + uvx.exe at the archive root, so we can
# Expand-Archive directly into bin/.
#
# Version is pinned (not "latest") so a future uv release with breaking
# behavior can't silently change `uv sync --extra` semantics underneath us.
# Override with $env:UV_VERSION when you want to test a newer uv.
# Pass -Force to re-download over an already-installed binary -- e.g. after
# bumping $DefaultUvVersion above.

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$DefaultUvVersion = "0.11.8"
$UvVersion = if ($env:UV_VERSION) { $env:UV_VERSION } else { $DefaultUvVersion }

# Project root = parent of this script's parent (scripts/.. -> project)
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BinDir = Join-Path $ProjectRoot "bin"
$UvBin  = Join-Path $BinDir "uv.exe"
$ChecksumManifest = Join-Path $ProjectRoot "scripts/uv-checksums.txt"

if ((Test-Path $UvBin) -and -not $Force) {
    Write-Host "[OK] uv already present at $UvBin"
    exit 0
}

# Architecture detection. Windows on ARM still ships x86_64 emulation, so we
# match $env:PROCESSOR_ARCHITECTURE precisely; fall back to x86_64 if unknown.
$arch = switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { "x86_64" }
    "ARM64" { "aarch64" }
    "x86"   { "i686" }
    default { "x86_64" }
}
$triple = "$arch-pc-windows-msvc"
$url    = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-$triple.zip"

Write-Host "[INFO] Downloading uv $UvVersion ($triple) from $url"

function Get-ExpectedUvArchiveHash {
    param(
        [string]$ManifestPath,
        [string]$Version,
        [string]$TargetTriple
    )

    if (-not (Test-Path $ManifestPath)) {
        return $null
    }

    foreach ($line in Get-Content $ManifestPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed -split '\s+'
        if ($parts.Count -ge 4 -and $parts[0] -eq $Version -and $parts[1] -eq $TargetTriple -and $parts[2] -eq "archive") {
            return $parts[3].ToLower()
        }
    }

    return $null
}

if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir | Out-Null
}

$tmpZip = Join-Path $env:TEMP ("uv-bootstrap-" + [Guid]::NewGuid().ToString() + ".zip")
$renamed = @()
try {
    # Use Tls12 explicitly for older PowerShell hosts that default to SSL3/TLS1.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $tmpZip -UseBasicParsing
    $expected = Get-ExpectedUvArchiveHash -ManifestPath $ChecksumManifest -Version $UvVersion -TargetTriple $triple
    if ([string]::IsNullOrWhiteSpace($expected)) {
        if ($env:UV_ALLOW_UNVERIFIED) {
            Write-Warning "uv archive checksum is not registered; continuing because UV_ALLOW_UNVERIFIED is set"
        } else {
            throw "uv archive checksum is not registered. Run scripts/update_uv_checksums.sh or set UV_ALLOW_UNVERIFIED=1"
        }
    } else {
        $actual = (Get-FileHash -Algorithm SHA256 $tmpZip).Hash.ToLower()
        if ($actual -ne $expected) {
            throw "uv archive checksum mismatch; possible supply-chain tampering. expected=$expected actual=$actual"
        }
    }

    if ($Force) {
        # Force-updating over an already-running bin\uv.exe: Windows refuses
        # to overwrite an executable's bytes while it's mapped in, but a
        # rename-aside is allowed (same trick self-updaters use). Tracked in
        # $renamed so a failure below rolls back instead of stranding bin/
        # without a working uv.exe (failure-atomicity).
        # Backup names include $PID so two concurrent -Force invocations never
        # share the same rename-aside target and clobber each other's backup.
        foreach ($name in @("uv.exe", "uvx.exe")) {
            $target = Join-Path $BinDir $name
            if (Test-Path $target) {
                $old = "$target.old.$PID"
                Remove-Item $old -Force -ErrorAction SilentlyContinue
                Rename-Item -Path $target -NewName (Split-Path -Leaf $old) -ErrorAction Stop
                $renamed += [PSCustomObject]@{ Original = $target; Backup = $old }
            }
        }
    }

    Expand-Archive -Path $tmpZip -DestinationPath $BinDir -Force

    if (-not (Test-Path $UvBin)) {
        throw "uv.exe was not produced by the archive at $url"
    }

    # Success: drop the backups.
    foreach ($r in $renamed) { Remove-Item $r.Backup -Force -ErrorAction SilentlyContinue }
} catch {
    # Roll back any rename-asides so a failed update doesn't strand bin/
    # without a working uv.exe -- even when Expand-Archive partially wrote a
    # new (possibly truncated/corrupt) file before failing.
    foreach ($r in $renamed) {
        if (Test-Path $r.Backup) {
            Remove-Item $r.Original -Force -ErrorAction SilentlyContinue
            Rename-Item -Path $r.Backup -NewName (Split-Path -Leaf $r.Original) -ErrorAction SilentlyContinue
        }
    }
    Write-Error $_
    exit 1
} finally {
    if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue }
}

Write-Host "[OK] uv installed: $UvBin"
& $UvBin --version

