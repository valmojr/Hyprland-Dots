#!/usr/bin/env bash

source "$HOME/.config/hypr/scripts/wallpaper_backend.sh" || exit 0

if wallpaper_query >/dev/null 2>&1; then
  wallpaper_restore >/dev/null 2>&1 || true
  exit 0
fi

"$WALLPAPER_DAEMON_CMD" --format xrgb &
daemon_pid=$!

for _ in {1..50}; do
  wallpaper_query >/dev/null 2>&1 && break
  sleep 0.1
done

wallpaper_restore >/dev/null 2>&1 || true
wait "$daemon_pid"
