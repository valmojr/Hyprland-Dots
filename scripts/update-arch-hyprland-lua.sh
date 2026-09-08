#!/usr/bin/env bash
# One-command Arch Linux updater for this fork's Lua Hyprland configuration.
# It deliberately asks before package and configuration changes.

set -Eeuo pipefail

REPOSITORY="https://github.com/valmojr/Hyprland-Dots.git"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/hyprland-dots-update.XXXXXX")"

cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nError: %s\n' "$*" >&2; exit 1; }
confirm() {
  local reply
  read -r -p "$1 [Y/n] " reply
  [[ ! "$reply" =~ ^[Nn]$ ]]
}

command -v pacman >/dev/null 2>&1 || die "This script is only for Arch Linux."
command -v Hyprland >/dev/null 2>&1 || die "Hyprland is not installed."
command -v git >/dev/null 2>&1 || die "Install git and run this script again: sudo pacman -S git"
command -v python3 >/dev/null 2>&1 || die "Install Python and run this script again: sudo pacman -S python"

hypr_version=$(pacman -Q hyprland 2>/dev/null | awk '{print $2}' | sed 's/-.*//')
[[ -n "$hypr_version" ]] || die "The hyprland package was not found by pacman."
if (( $(vercmp "$hypr_version" "0.55.0") < 0 )); then
  die "Hyprland $hypr_version is too old. Update the system and try again: sudo pacman -Syu"
fi

say "This assistant will temporarily download valmojr/Hyprland-Dots, install a compatible Waybar, and convert ~/.config/hypr to Lua."
say "The conversion is activated only after Hyprland validates it; the old configuration is preserved at ~/.config/hypr-pre-lua-DATE."
confirm "Continue?" || { say "Cancelled; nothing was changed."; exit 0; }

if command -v yay >/dev/null 2>&1; then
  aur_helper=(yay)
elif command -v paru >/dev/null 2>&1; then
  aur_helper=(paru)
else
  die "Install yay or paru to install waybar-git, then run this script again."
fi

if ! pacman -Q waybar-git >/dev/null 2>&1; then
  say "Waybar 0.15 does not support workspace clicks with Lua configuration. waybar-git will be installed; confirm removal of waybar if the package manager asks."
  confirm "Install/update waybar-git now?" || die "The update was cancelled because waybar-git is required."
  "${aur_helper[@]}" -S --needed waybar-git
elif ! waybar --version >/dev/null 2>&1; then
  say "waybar-git cannot start. This usually means an Arch shared library was updated and Waybar must be rebuilt."
  confirm "Rebuild waybar-git now?" || die "The update was cancelled because Waybar is not runnable."
  "${aur_helper[@]}" -S --rebuild waybar-git
fi

if ! waybar --version >/dev/null 2>&1; then
  die "waybar-git still cannot start after installation/rebuild. Run: ${aur_helper[0]} -S --rebuild waybar-git"
fi

say "Downloading the current converter"
git clone --depth=1 "$REPOSITORY" "$WORKDIR/dots"
MIGRATOR="$WORKDIR/dots/scripts/migrate-hyprland-to-lua.py"
[[ -x "$MIGRATOR" ]] || die "The downloaded repository does not contain the Lua converter."

if [[ -f "$HOME/.config/hypr/hyprland.conf" ]]; then
  say "Hyprlang configuration detected; creating a validated Lua tree."
  python3 "$MIGRATOR" --config-dir "$HOME/.config/hypr" --template-dir "$WORKDIR/dots/config/hypr"
elif [[ -f "$HOME/.config/hypr/hyprland.lua" ]]; then
  say "The configuration already uses Lua; validating it."
  Hyprland --verify-config --config "$HOME/.config/hypr/hyprland.lua"
else
  die "Could not find ~/.config/hypr/hyprland.conf or hyprland.lua. Nothing was changed."
fi

if command -v hyprctl >/dev/null 2>&1 && hyprctl instances -j >/dev/null 2>&1; then
  if confirm "Reload the Hyprland configuration now?"; then
    hyprctl reload
    say "Configuration reloaded. If anything looks wrong, log out and back in."
  fi
fi

say "Done. Check ~/.config/hypr/migration-report.json when a conversion was performed."
