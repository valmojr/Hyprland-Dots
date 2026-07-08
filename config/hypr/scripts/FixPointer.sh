#!/usr/bin/env bash
set -euo pipefail

# Give Aquamarine/libinput time to finish registering the I2C touchpad.
sleep 2

apply_keyword() {
  local key="$1"
  local value="$2"

  for _ in 1 2 3 4 5; do
    if hyprctl -q keyword "$key" "$value" -r; then
      return 0
    fi
    sleep 1
  done
}

apply_keyword input:touchpad:disable_while_typing false
apply_keyword cursor:no_warps false
apply_keyword 'device[pixa3848:00-093a:3848-touchpad]:enabled' true
apply_keyword 'device[pixa3848:00-093a:3848-mouse]:enabled' true
