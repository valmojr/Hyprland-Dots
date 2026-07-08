#!/usr/bin/env bash

set -u

ICON_CONNECTED="󰖂"
ICON_DISCONNECTED="󰖪"
ICON_MISSING="󰖩"

json_escape() {
    local value=${1-}
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/}
    printf '%s' "$value"
}

emit() {
    local text=$1
    local class=$2
    local tooltip=$3

    printf '{"text":"%s","class":"%s","tooltip":"%s"}\n' \
        "$(json_escape "$text")" \
        "$(json_escape "$class")" \
        "$(json_escape "$tooltip")"
}

status_text() {
    if ! command -v tailscale >/dev/null 2>&1; then
        emit "$ICON_MISSING" "missing" "Tailscale nao esta instalado"
        return
    fi

    local status_output status_code ip tooltip
    status_output=$(timeout 2 tailscale status --peers=false 2>&1)
    status_code=$?

    if [[ $status_code -eq 0 ]]; then
        ip=$(timeout 2 tailscale ip -4 2>/dev/null | head -n 1)
        tooltip="Tailscale: conectado"
        [[ -n "$ip" ]] && tooltip+="\nIP: $ip"
        tooltip+="\nClique: mostrar status\nClique direito: admin console"
        emit "$ICON_CONNECTED" "connected" "$tooltip"
        return
    fi

    if [[ $status_code -eq 124 ]]; then
        emit "$ICON_DISCONNECTED" "timeout" "Tailscale: sem resposta do daemon"
        return
    fi

    tooltip="Tailscale: desconectado"
    [[ -n "$status_output" ]] && tooltip+="\n$status_output"
    tooltip+="\nClique: mostrar status\nClique direito: admin console"
    emit "$ICON_DISCONNECTED" "disconnected" "$tooltip"
}

notify_status() {
    local body

    if ! command -v tailscale >/dev/null 2>&1; then
        notify-send "Tailscale" "tailscale nao esta instalado"
        return
    fi

    body=$(timeout 3 tailscale status 2>&1 | sed -n '1,14p')
    [[ -z "$body" ]] && body="Sem retorno do tailscale status"
    notify-send "Tailscale" "$body"
}

case "${1:-status}" in
    status)
        status_text
        ;;
    notify)
        notify_status
        ;;
    *)
        printf 'Usage: %s {status|notify}\n' "$0" >&2
        exit 1
        ;;
esac
