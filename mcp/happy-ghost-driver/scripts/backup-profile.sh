#!/usr/bin/env bash
# Back up / restore the automation Chrome profile.
#
# Why this exists: the profile IS the logged-in identity. Losing it forces a
# manual re-login, which the site sees as a new device — the single highest
# risk signal for a personal account. A profile you cannot restore is a
# profile you will eventually lose.
#
# Chrome must be closed: the profile holds live SQLite databases (Cookies,
# Login Data, History) and copying them mid-write yields a corrupt restore.
#
# Usage:
#   bash scripts/backup-profile.sh              # take a backup, rotate old ones
#   bash scripts/backup-profile.sh list         # show existing backups
#   bash scripts/backup-profile.sh restore      # restore the newest backup
#   bash scripts/backup-profile.sh restore <name>
#   bash scripts/backup-profile.sh migrate      # adopt the old $TMPDIR profile
#
# Env:
#   GHOST_HOME          default $HOME/.ghost-driver
#   GHOST_PROFILE_DIR   default $GHOST_HOME/chrome-profile
#   GHOST_BACKUP_KEEP   how many backups to retain (default 5)

set -euo pipefail

GHOST_HOME="${GHOST_HOME:-$HOME/.ghost-driver}"
PROFILE_DIR="${GHOST_PROFILE_DIR:-$GHOST_HOME/chrome-profile}"
BACKUP_ROOT="${GHOST_BACKUP_ROOT:-$GHOST_HOME/backups}"
KEEP="${GHOST_BACKUP_KEEP:-5}"

die() { echo "[backup-profile] $*" >&2; exit 1; }

# Refuse to touch the profile while Chrome still has it open.
#
# Matches the profile's basename rather than the full path, because a path
# assembled from an env var with a trailing slash appears doubled in Chrome's
# command line and would slip past a full-path pattern. A missed match here
# means copying live SQLite files, which is exactly the failure this prevents.
assert_chrome_closed() {
  if pgrep -f -- "$(basename "$PROFILE_DIR")" >/dev/null 2>&1; then
    die "Chrome is still running with this profile.
  Quit it first (the profile's SQLite files must not be copied mid-write).
  Profile: $PROFILE_DIR"
  fi
}

cmd_backup() {
  [[ -d "$PROFILE_DIR" ]] || die "No profile at $PROFILE_DIR — nothing to back up."
  assert_chrome_closed

  local stamp dest
  stamp="$(date +%Y%m%d-%H%M%S)"
  dest="$BACKUP_ROOT/$stamp"
  mkdir -p "$dest"

  echo "[backup-profile] Copying $PROFILE_DIR -> $dest"
  # Cache/ and GPUCache/ are large, worthless for identity, and slow the copy.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude 'Default/Cache/' \
      --exclude 'Default/Code Cache/' \
      --exclude 'Default/GPUCache/' \
      --exclude 'Default/Service Worker/CacheStorage/' \
      --exclude 'GrShaderCache/' \
      --exclude 'ShaderCache/' \
      "$PROFILE_DIR/" "$dest/"
  else
    cp -R "$PROFILE_DIR/." "$dest/"
  fi

  echo "[backup-profile] Done: $dest ($(du -sh "$dest" | cut -f1))"
  rotate
}

rotate() {
  [[ -d "$BACKUP_ROOT" ]] || return 0
  local -a all
  # Newest first, so anything past $KEEP is the stale tail.
  while IFS= read -r line; do all+=("$line"); done < <(ls -1 "$BACKUP_ROOT" 2>/dev/null | sort -r)
  local count=${#all[@]}
  if (( count <= KEEP )); then
    echo "[backup-profile] $count backup(s) retained (keep=$KEEP)."
    return 0
  fi
  local i
  for (( i = KEEP; i < count; i++ )); do
    echo "[backup-profile] Pruning old backup: ${all[$i]}"
    rm -rf "$BACKUP_ROOT/${all[$i]}"
  done
}

cmd_list() {
  [[ -d "$BACKUP_ROOT" ]] || { echo "[backup-profile] No backups yet at $BACKUP_ROOT"; return 0; }
  echo "[backup-profile] Backups in $BACKUP_ROOT (newest first):"
  ls -1 "$BACKUP_ROOT" | sort -r | while read -r name; do
    printf '  %-20s %s\n' "$name" "$(du -sh "$BACKUP_ROOT/$name" 2>/dev/null | cut -f1)"
  done
}

cmd_restore() {
  local name="${1:-}"
  [[ -d "$BACKUP_ROOT" ]] || die "No backups at $BACKUP_ROOT"
  if [[ -z "$name" ]]; then
    name="$(ls -1 "$BACKUP_ROOT" | sort -r | head -n 1)"
    [[ -n "$name" ]] || die "No backups to restore."
  fi
  local src="$BACKUP_ROOT/$name"
  [[ -d "$src" ]] || die "Backup not found: $src"
  assert_chrome_closed

  # Park the current profile instead of deleting it: if this restore turns
  # out to be the wrong snapshot, the live state is still recoverable.
  if [[ -d "$PROFILE_DIR" ]]; then
    local parked="$PROFILE_DIR.replaced-$(date +%Y%m%d-%H%M%S)"
    echo "[backup-profile] Moving current profile aside -> $parked"
    mv "$PROFILE_DIR" "$parked"
  fi

  echo "[backup-profile] Restoring $src -> $PROFILE_DIR"
  mkdir -p "$PROFILE_DIR"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$src/" "$PROFILE_DIR/"
  else
    cp -R "$src/." "$PROFILE_DIR/"
  fi
  echo "[backup-profile] Restored. Launch with: bash scripts/launch-chrome.sh"
}

# One-time migration for profiles created before the move to $HOME.
#
# The old location was "${TMPDIR}ghost-driver-chrome-profile", which macOS
# purges. Carrying that profile over preserves whatever sessions are already
# logged in there — which is the entire point: starting fresh instead would
# force a re-login, and a re-login is the "new device" event this whole change
# exists to avoid.
cmd_migrate() {
  # $TMPDIR carries a trailing slash on macOS; strip it so the path we print
  # (and pgrep against) matches what Chrome actually shows.
  local base="${TMPDIR:-/tmp}"
  local legacy="${base%/}/ghost-driver-chrome-profile"
  [[ -d "$legacy" ]] || die "No legacy profile found at:
  $legacy
  Nothing to migrate; just run scripts/launch-chrome.sh and log in once."

  if [[ -d "$PROFILE_DIR" ]]; then
    die "A profile already exists at $PROFILE_DIR.
  Refusing to overwrite it. If you meant to replace it, move it aside first:
    mv '$PROFILE_DIR' '$PROFILE_DIR.old'"
  fi

  # Match on the directory NAME, not the full path: the old launcher built the
  # path from $TMPDIR (which carries a trailing slash), so a running Chrome
  # shows a doubled slash that a full-path pattern silently fails to match —
  # and a missed match here means copying live SQLite files.
  if pgrep -f -- 'ghost-driver-chrome-profile' >/dev/null 2>&1; then
    die "Chrome is still running with the legacy profile.
  Quit it first, then re-run: bash scripts/backup-profile.sh migrate
  Copying a live profile corrupts its Cookies / Login Data databases.
  Legacy: $legacy"
  fi

  echo "[backup-profile] Migrating legacy profile:"
  echo "[backup-profile]   from $legacy"
  echo "[backup-profile]   to   $PROFILE_DIR"
  mkdir -p "$(dirname "$PROFILE_DIR")"
  if command -v rsync >/dev/null 2>&1; then
    mkdir -p "$PROFILE_DIR"
    rsync -a \
      --exclude 'Default/Cache/' \
      --exclude 'Default/Code Cache/' \
      --exclude 'Default/GPUCache/' \
      --exclude 'Default/Service Worker/CacheStorage/' \
      --exclude 'GrShaderCache/' \
      --exclude 'ShaderCache/' \
      "$legacy/" "$PROFILE_DIR/"
  else
    cp -R "$legacy" "$PROFILE_DIR"
  fi

  # Date the profile from when it was originally CREATED, not last written.
  # mtime would be "just now" (Chrome writes on every shutdown), which would
  # make the budget guard treat a long-established profile as a brand-new one
  # and throttle it through a warm-up it already served.
  if [[ ! -f "$PROFILE_DIR/.ghost-created-at" ]]; then
    local epoch born
    epoch="$(stat -f %B "$legacy" 2>/dev/null || stat -c %W "$legacy" 2>/dev/null || echo 0)"
    # Linux reports 0 when the filesystem has no birth time; fall back to mtime.
    if [[ -z "$epoch" || "$epoch" == "0" ]]; then
      epoch="$(stat -f %m "$legacy" 2>/dev/null || stat -c %Y "$legacy" 2>/dev/null || echo 0)"
    fi
    if [[ "$epoch" != "0" ]]; then
      born="$(date -u -r "$epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d "@$epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo '')"
    fi
    [[ -n "${born:-}" ]] || born="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "$born" > "$PROFILE_DIR/.ghost-created-at"
    echo "[backup-profile] Recorded profile birth date: $born"
  fi

  echo "[backup-profile] Done. Verify your logins, then back it up:"
  echo "[backup-profile]   bash scripts/launch-chrome.sh"
  echo "[backup-profile]   bash scripts/backup-profile.sh"
  echo "[backup-profile] The legacy copy was left in place; delete it once satisfied:"
  echo "[backup-profile]   rm -rf '$legacy'"
}

case "${1:-backup}" in
  backup)  cmd_backup ;;
  list)    cmd_list ;;
  restore) shift; cmd_restore "${1:-}" ;;
  migrate) cmd_migrate ;;
  *)       die "Unknown command: $1 (expected backup|list|restore|migrate)" ;;
esac
