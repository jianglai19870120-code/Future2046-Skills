param(
  [string]$SkillId = '',
  [string]$InstallRoot = (Join-Path $env:USERPROFILE '.codex\skills')
)

$ErrorActionPreference = 'Stop'
function Get-Sha256([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  try {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '') }
    finally { $hash.Dispose() }
  }
  finally { $stream.Dispose() }
}
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$registryPath = Join-Path $repoRoot 'shared\skill-registry.yaml'
$registryJson = python (Join-Path $repoRoot 'tools\read_registry.py') $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Skill registry; install root requirements.txt first.' }
$catalogCheck = python (Join-Path $repoRoot 'tools\generate_router_catalog.py') --root $repoRoot --check
if ($LASTEXITCODE -ne 0) { throw 'Router catalog is stale. Run python tools/generate_router_catalog.py --write.' }
$entries = @()
foreach ($item in (ConvertFrom-Json -InputObject $registryJson)) { $entries += $item }
if ($SkillId) {
  $selected = @($entries | Where-Object { $_.id -eq $SkillId })
  if ($selected.Count -eq 0) { throw "Skill not registered: $SkillId" }
  if ($SkillId -ne 'future2046') { $selected += @($entries | Where-Object { $_.id -eq 'future2046' }) }
  $entries = $selected
}
else { $entries = @($entries | Where-Object { $_.status -eq 'stable' -and $_.distribution -eq 'public' }) }
if ($entries.Count -eq 0) { throw "Skill not registered: $SkillId" }
$installPath = [IO.Path]::GetFullPath($InstallRoot)
New-Item -ItemType Directory -Force -Path $installPath | Out-Null

foreach ($entry in $entries) {
  if ('codex' -notin @($entry.supported_agents)) { if ($SkillId) { throw "Skill does not support Codex: $SkillId" }; continue }
  $name = [string]$entry.package_directory
  if ($name -notmatch '^Future2046-[a-z0-9-]+$') { throw "Invalid package directory: $name" }
  $source = [IO.Path]::GetFullPath((Join-Path $repoRoot $entry.package_path))
  $target = [IO.Path]::GetFullPath((Join-Path $installPath $name))
  if (-not $source.StartsWith(([IO.Path]::GetFullPath((Join-Path $repoRoot 'skills')) + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) { throw 'Source outside skills directory.' }
  if ((Split-Path -Parent $target) -ne $installPath) { throw 'Target outside install root.' }
  if (Test-Path -LiteralPath $target) {
    $existing = Join-Path $target 'SKILL.md'
    if (-not (Test-Path -LiteralPath $existing)) { throw "Existing target is not an installed Skill: $target" }
    $content = Get-Content -Raw -LiteralPath $existing
    if ($content -notmatch ('(?m)^name:\s*' + [regex]::Escape([string]$entry.id) + '\s*$')) { throw "Existing target belongs to another Skill: $target" }
  }
  $sourceFiles = @{}
  Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object { $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -notin '.pyc','.pyo' } | ForEach-Object {
    $key = $_.FullName.Substring($source.Length).TrimStart('\')
    $sourceFiles[$key] = $_.FullName
  }
  $targetFiles = @{}
  if (Test-Path -LiteralPath $target) {
    Get-ChildItem -LiteralPath $target -Recurse -File | ForEach-Object {
      $key = $_.FullName.Substring($target.Length).TrimStart('\')
      $targetFiles[$key] = $_.FullName
    }
  }
  $added = @($sourceFiles.Keys | Where-Object { -not $targetFiles.ContainsKey($_) })
  $stale = @($targetFiles.Keys | Where-Object { -not $sourceFiles.ContainsKey($_) })
  $changed = @($sourceFiles.Keys | Where-Object { $targetFiles.ContainsKey($_) -and (Get-Sha256 $sourceFiles[$_]) -ne (Get-Sha256 $targetFiles[$_]) })
  Write-Output "$($entry.id): add=$($added.Count) change=$($changed.Count) remove=$($stale.Count)"
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  foreach ($key in @($added) + @($changed)) {
    $dest = Join-Path $target $key
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    Copy-Item -LiteralPath $sourceFiles[$key] -Destination $dest -Force
  }
  foreach ($key in $stale) { Remove-Item -LiteralPath $targetFiles[$key] -Force }
  python (Join-Path $repoRoot 'tools\verify_codex_install.py') --source $source --target $target
  if ($LASTEXITCODE -ne 0) { throw "Codex install verification failed: $($entry.id)" }
}
