# Set up Claude Code memory sync for this repository.
#
# What this does:
#   1. Registers the LLM merge driver in the local .git/config
#   2. Sets autoMemoryDirectory in ~/.claude/settings.json to .claude/memory/
#   3. Migrates any existing memories from the Claude Code default location
#
# Run once after git clone (or when re-setting up a machine).
# Safe to re-run — all operations are idempotent.

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$MemoryDir   = Join-Path $ProjectRoot '.claude\memory'
$UserSettings = Join-Path $env:USERPROFILE '.claude\settings.json'

function Log-Ok($m)   { Write-Host "[OK]   $m" }
function Log-Info($m) { Write-Host "[INFO] $m" }
function Log-Skip($m) { Write-Host "[SKIP] $m" }

# ── 1. Register LLM merge driver in local .git/config ────────────────────────
$uvBin = Join-Path $ProjectRoot 'bin\uv.exe'
if (-not (Test-Path $uvBin)) { $uvBin = 'uv' }  # fall back to PATH

$driverCmd = "$uvBin run python .claude/scripts/merge-memory.py %O %A %B %P"

git -C $ProjectRoot config merge.llm-memory.name 'LLM-based memory merge'
git -C $ProjectRoot config merge.llm-memory.driver $driverCmd
Log-Ok "Registered git merge driver: llm-memory"

# ── 2. Set autoMemoryDirectory in ~/.claude/settings.json ─────────────────────
$claudeDir = Split-Path $UserSettings
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
if (-not (Test-Path $UserSettings)) { '{}' | Set-Content $UserSettings -Encoding UTF8 }

$result = & $uvBin run python - @"
import json, pathlib

settings_path = pathlib.Path(r'$UserSettings')
memory_dir    = r'$MemoryDir'

try:
    settings = json.loads(settings_path.read_text(encoding='utf-8'))
except Exception:
    settings = {}

current = settings.get('autoMemoryDirectory', '')
if current == memory_dir:
    print('[SKIP] autoMemoryDirectory already set')
else:
    settings['autoMemoryDirectory'] = memory_dir
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8'
    )
    print(f'[OK]   autoMemoryDirectory -> {memory_dir}')
"@
Write-Host $result

# ── 3. Migrate existing memories from Claude Code default location ─────────────
New-Item -ItemType Directory -Force -Path $MemoryDir | Out-Null

$projectName = Split-Path $ProjectRoot -Leaf
$candidates = @(
    Join-Path $env:USERPROFILE ".claude\projects\$projectName\memory",
    Join-Path $env:USERPROFILE '.claude\projects\O--yu-ai-manager\memory'
)

foreach ($candidate in $candidates) {
    if ((Test-Path $candidate) -and $candidate -ne $MemoryDir) {
        $files = Get-ChildItem $candidate -Filter '*.md' -ErrorAction SilentlyContinue
        if ($files.Count -gt 0) {
            Log-Info "Found $($files.Count) memory files in $candidate — migrating"
            foreach ($f in $files) {
                $dest = Join-Path $MemoryDir $f.Name
                if (-not (Test-Path $dest)) {
                    Copy-Item $f.FullName $dest
                    Log-Ok "  $($f.Name)"
                }
            }
            break
        }
    }
}

Log-Ok "Memory sync setup complete. New location: $MemoryDir"
Log-Info "Restart Claude Code for autoMemoryDirectory to take effect."
