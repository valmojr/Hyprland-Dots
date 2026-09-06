#!/usr/bin/env bash
set -euo pipefail

# Give Aquamarine/libinput time to finish registering the I2C touchpad.
sleep 2

apply_lua() {
  local code="$1"

  for _ in 1 2 3 4 5; do
    if hyprctl -q eval "$code"; then
      return 0
    fi
    sleep 1
  done
}

apply_lua 'hl.config({ input = { touchpad = { disable_while_typing = false } } })'
apply_lua 'hl.config({ cursor = { no_warps = false } })'
apply_lua 'hl.device({ name = "pixa3848:00-093a:3848-touchpad", enabled = true })'
apply_lua 'hl.device({ name = "pixa3848:00-093a:3848-mouse", enabled = true })'
