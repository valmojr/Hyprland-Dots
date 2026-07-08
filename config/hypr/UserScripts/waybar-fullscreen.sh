#!/usr/bin/env bash

win=$(hyprctl -j activewindow)
mon=$(hyprctl -j monitors | jq '.[] | select(.focused)')

wx=$(echo "$win" | jq '.size[0]')
wy=$(echo "$win" | jq '.size[1]')
fs=$(echo "$win" | jq '.fullscreen')

mw=$(echo "$mon" | jq '.width')
mh=$(echo "$mon" | jq '.height')
rt=$(echo "$mon" | jq '.reserved[0]')
rr=$(echo "$mon" | jq '.reserved[1]')
rb=$(echo "$mon" | jq '.reserved[2]')
rl=$(echo "$mon" | jq '.reserved[3]')

work_w=$((mw - rl - rr))
work_h=$((mh - rt - rb))

if [[ "$fs" != "0" ]]; then
  echo '{"class":"full"}'
elif [[ "$wx" -ge "$work_w" && "$wy" -ge "$work_h" ]]; then
  echo '{"class":"full"}'
else
  echo '{"class":"normal"}'
fi
