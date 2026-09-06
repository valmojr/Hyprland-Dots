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
die() { printf '\nErro: %s\n' "$*" >&2; exit 1; }
confirm() {
  local reply
  read -r -p "$1 [S/n] " reply
  [[ ! "$reply" =~ ^[Nn]$ ]]
}

command -v pacman >/dev/null 2>&1 || die "Este script é exclusivo para Arch Linux."
command -v Hyprland >/dev/null 2>&1 || die "Hyprland não está instalado."
command -v git >/dev/null 2>&1 || die "Instale git e execute novamente: sudo pacman -S git"
command -v python3 >/dev/null 2>&1 || die "Instale Python e execute novamente: sudo pacman -S python"

hypr_version=$(pacman -Q hyprland 2>/dev/null | awk '{print $2}' | sed 's/-.*//')
[[ -n "$hypr_version" ]] || die "O pacote hyprland não foi encontrado pelo pacman."
if (( $(vercmp "$hypr_version" "0.55.0") < 0 )); then
  die "Hyprland $hypr_version é antigo. Atualize o sistema e tente novamente: sudo pacman -Syu"
fi

say "Este assistente vai baixar temporariamente valmojr/Hyprland-Dots, instalar Waybar compatível e converter ~/.config/hypr para Lua."
say "A conversão só é ativada se Hyprland validá-la; a configuração anterior é preservada em ~/.config/hypr-pre-lua-DATA."
confirm "Continuar?" || { say "Cancelado; nada foi alterado."; exit 0; }

if ! pacman -Q waybar-git >/dev/null 2>&1; then
  if command -v yay >/dev/null 2>&1; then
    aur_helper=(yay -S --needed)
  elif command -v paru >/dev/null 2>&1; then
    aur_helper=(paru -S --needed)
  else
    die "Instale yay ou paru para instalar waybar-git e execute novamente."
  fi
  say "Waybar 0.15 não suporta clique em workspaces com a configuração Lua. Será instalado waybar-git; confirme a remoção de waybar, se o gerenciador perguntar."
  confirm "Instalar/atualizar waybar-git agora?" || die "Sem waybar-git, a atualização foi cancelada."
  "${aur_helper[@]}" waybar-git
fi

say "Baixando o conversor atualizado"
git clone --depth=1 "$REPOSITORY" "$WORKDIR/dots"
MIGRATOR="$WORKDIR/dots/scripts/migrate-hyprland-to-lua.py"
[[ -x "$MIGRATOR" ]] || die "O conversor Lua não existe no repositório baixado."

if [[ -f "$HOME/.config/hypr/hyprland.conf" ]]; then
  say "Configuração Hyprlang detectada; criando uma árvore Lua validada."
  python3 "$MIGRATOR" --config-dir "$HOME/.config/hypr" --template-dir "$WORKDIR/dots/config/hypr"
elif [[ -f "$HOME/.config/hypr/hyprland.lua" ]]; then
  say "A configuração já usa Lua; validando-a."
  Hyprland --verify-config --config "$HOME/.config/hypr/hyprland.lua"
else
  die "Não encontrei ~/.config/hypr/hyprland.conf nem hyprland.lua. Nenhuma alteração foi feita."
fi

if command -v hyprctl >/dev/null 2>&1 && hyprctl instances -j >/dev/null 2>&1; then
  if confirm "Recarregar a configuração do Hyprland agora?"; then
    hyprctl reload
    say "Configuração recarregada. Se algo parecer estranho, termine a sessão e entre novamente."
  fi
fi

say "Concluído. Confira o migration-report.json em ~/.config/hypr quando uma conversão foi feita."
