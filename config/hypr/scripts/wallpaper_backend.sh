#!/usr/bin/env bash

if command -v swww >/dev/null 2>&1 && command -v swww-daemon >/dev/null 2>&1; then
  WALLPAPER_CMD="swww"
  WALLPAPER_DAEMON_CMD="swww-daemon"
  WALLPAPER_CACHE_DIR="$HOME/.cache/swww"
elif command -v awww >/dev/null 2>&1 && command -v awww-daemon >/dev/null 2>&1; then
  WALLPAPER_CMD="awww"
  WALLPAPER_DAEMON_CMD="awww-daemon"
  WALLPAPER_CACHE_DIR="$HOME/.cache/awww"
else
  echo "No supported wallpaper backend found (need swww or awww)." >&2
  return 1 2>/dev/null || exit 1
fi

wallpaper_query() {
  "$WALLPAPER_CMD" query "$@"
}

wallpaper_img() {
  "$WALLPAPER_CMD" img "$@"
}

wallpaper_restore() {
  "$WALLPAPER_CMD" restore "$@"
}

wallpaper_kill() {
  "$WALLPAPER_CMD" kill "$@"
}

wallpaper_ensure_daemon() {
  wallpaper_query >/dev/null 2>&1 || "$WALLPAPER_DAEMON_CMD" --format xrgb
}
