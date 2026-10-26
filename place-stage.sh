#!/bin/bash
# Move the front window of Terminal, a browser, or the frontmost app
# onto the lower-left stage that OBS is cropped to.
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

TARGET="${1:-terminal}"
case "$TARGET" in
  terminal|Terminal) APP="Terminal" ;;
  chrome|Chrome|google-chrome) APP="Google Chrome" ;;
  safari|Safari) APP="Safari" ;;
  arc|Arc) APP="Arc" ;;
  firefox|Firefox) APP="Firefox" ;;
  front|.) APP="" ;;
  *) APP="$TARGET" ;;
esac

if [[ -z "$APP" ]]; then
  APP=$(osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true')
fi

if [[ "$APP" == "OBS" ]]; then
  echo "OBS is in front. Focus Terminal or the browser, or pass its name." >&2
  exit 1
fi

osascript << EOF
tell application "$APP"
  activate
  if (count of windows) is 0 then error "No window"
  set bounds of front window to {$LEFT, $TOP, $RIGHT, $BOTTOM}
end tell
EOF

echo "Placed ${APP} at ${LEFT},${TOP} size $((RIGHT - LEFT))x$((BOTTOM - TOP))."
echo "That rectangle is the whole YouTube frame. The circle covers its upper right."
