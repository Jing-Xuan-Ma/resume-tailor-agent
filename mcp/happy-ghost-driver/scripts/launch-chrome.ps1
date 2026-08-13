# Launch Chrome with --remote-debugging-port=9222 on Windows.
# If 9222 is already in use, prints a hint and exits without launching.
#
# PROFILE PERSISTENCE (account-safety critical)
#   The user-data-dir holds the logged-in session, so it lives under the user
#   profile, NOT under $env:TEMP: losing it forces a re-login, which sites see
#   as a brand-new device — a high-weight risk signal for a personal account.
#   Back it up before touching it.
#
#   Chrome 136+ ignores --remote-debugging-port when it points at the default
#   Chrome data directory, so a dedicated profile is the only supported shape.
#   Defaults must match scripts/launch-chrome.sh and src/config/paths.ts.

$ErrorActionPreference = "Stop"
$Port = 9222
$GhostHome = if ($env:GHOST_HOME) { $env:GHOST_HOME } else { Join-Path $env:USERPROFILE ".ghost-driver" }
$UserDataDir = if ($env:GHOST_PROFILE_DIR) { $env:GHOST_PROFILE_DIR } else { Join-Path $GhostHome "chrome-profile" }
$BirthMarker = Join-Path $UserDataDir ".ghost-created-at"

# Detect existing process bound to 9222.
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "[launch-chrome] Port $Port is already in use. Assuming Chrome is running."
    exit 0
}

# Locate chrome.exe
$ChromeCandidates = @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)
$ChromeBin = $null
foreach ($c in $ChromeCandidates) {
  if (Test-Path $c) { $ChromeBin = $c; break }
}
if (-not $ChromeBin) {
  Write-Error "[launch-chrome] chrome.exe not found in standard install locations."
  exit 1
}

$FirstRun = -not (Test-Path $BirthMarker)
if (-not (Test-Path $UserDataDir)) {
  New-Item -ItemType Directory -Path $UserDataDir -Force | Out-Null
}
if ($FirstRun) {
  (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") | Set-Content -Path $BirthMarker
  Write-Host "[launch-chrome] ============================================================"
  Write-Host "[launch-chrome]  NEW PROFILE CREATED - this Chrome is logged out."
  Write-Host "[launch-chrome]    $UserDataDir"
  Write-Host "[launch-chrome]"
  Write-Host "[launch-chrome]  To a site, this is a brand-new device. Before automating:"
  Write-Host "[launch-chrome]    1. Log in manually, by hand, in this window."
  Write-Host "[launch-chrome]    2. Browse normally for a few days (read-only)."
  Write-Host "[launch-chrome]    3. Only then let the agent perform write actions."
  Write-Host "[launch-chrome]"
  Write-Host "[launch-chrome]  NEVER delete this directory: losing it forces a re-login,"
  Write-Host "[launch-chrome]  which looks like a new device again."
  Write-Host "[launch-chrome] ============================================================"
}

Write-Host "[launch-chrome] Launching: $ChromeBin"
Write-Host "[launch-chrome]   --remote-debugging-port=$Port"
Write-Host "[launch-chrome]   --user-data-dir=$UserDataDir"

# Normal (not minimized) window: the foreground guard refuses to act on a tab
# that is not visible, and a minimized window reports visibilityState 'hidden'.
Start-Process -FilePath $ChromeBin `
  -ArgumentList `
    "--remote-debugging-port=$Port", `
    "--user-data-dir=`"$UserDataDir`"", `
    "--disable-blink-features=AutomationControlled", `
    "--disable-features=AutomationControlled", `
    "--disable-infobars", `
    "--no-first-run" `
  -WindowStyle Normal

Write-Host "[launch-chrome] Chrome launched."
