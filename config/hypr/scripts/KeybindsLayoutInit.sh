#!/usr/bin/env bash
# /* ---- 💫 https://github.com/JaKooLit 💫 ---- */  ##
# Initialize J/K keybinds so they always cycle windows globally (no layout-specific behavior)
# This avoids double-actions when layouts change.

set -euo pipefail

# Always reset and bind SUPER+J/K the same way on startup
hyprctl eval 'hl.unbind("SUPER + J"); hl.unbind("SUPER + K")' || true

# Cycle windows globally: J = next, K = previous
hyprctl eval 'hl.bind("SUPER + J", hl.dsp.window.cycle_next()); hl.bind("SUPER + K", hl.dsp.window.cycle_next({ prev = true }))'
