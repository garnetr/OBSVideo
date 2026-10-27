#!/bin/bash
# Move a window onto the lower-left stage that OBS is cropped to.
set -euo pipefail

STAGE="${HOME}/Library/Application Support/obs-studio/youtube-lower-left/stage.json"
if [[ ! -f "$STAGE" ]]; then
  echo "No stage yet. Run ./install-obs-setup.py first." >&2
  exit 1
fi

read -r LEFT TOP RIGHT BOTTOM < <(python3 - "$STAGE" << 'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
print(*doc["bounds"])
PY
)

WIDTH=$((RIGHT - LEFT))
HEIGHT=$((BOTTOM - TOP))

place_scriptable() {
  local app="$1"
  osascript << EOF
tell application "$app"
  activate
  if (count of windows) is 0 then error "No window"
  set bounds of front window to {$LEFT, $TOP, $RIGHT, $BOTTOM}
end tell
EOF
  echo "Placed ${app} at ${LEFT},${TOP} size ${WIDTH}x${HEIGHT}."
}

# Factorio has no window-bounds command. Its process window does take a size
# and a position. Size first, then position, so the resize does not shove it
# off the stage.
place_factorio() {
  osascript << EOF
tell application "System Events"
  if not (exists process "factorio") then error "Factorio is not running"
  tell process "factorio"
    set frontmost to true
    if (count of windows) is 0 then error "No window"
    set size of window 1 to {$WIDTH, $HEIGHT}
    delay 0.3
    set position of window 1 to {$LEFT, $TOP}
    set frontmost to true
  end tell
end tell
EOF
  echo "Placed Factorio at ${LEFT},${TOP} size ${WIDTH}x${HEIGHT}."
}

TARGET="${1:-terminal}"
case "$TARGET" in
  factorio|Factorio) place_factorio ;;
  terminal|Terminal) place_scriptable "Terminal" ;;
  chrome|Chrome|google-chrome) place_scriptable "Google Chrome" ;;
  safari|Safari) place_scriptable "Safari" ;;
  arc|Arc) place_scriptable "Arc" ;;
  firefox|Firefox) place_scriptable "Firefox" ;;
  front|.)
    APP=$(osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true')
    if [[ "$APP" == "OBS" || "$APP" == "factorio" ]]; then
      if [[ "$APP" == "factorio" ]]; then
        place_factorio
      else
        echo "OBS is in front. Focus Terminal, the browser, or Factorio, or pass its name." >&2
        exit 1
      fi
    else
      place_scriptable "$APP"
    fi
    ;;
  *)
    if [[ "$TARGET" == "OBS" ]]; then
      echo "OBS is in front. Focus Terminal, the browser, or Factorio, or pass its name." >&2
      exit 1
    fi
    place_scriptable "$TARGET"
    ;;
esac

echo "That rectangle is the whole YouTube frame. The circle covers its upper right."
