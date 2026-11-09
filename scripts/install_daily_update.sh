#!/bin/bash
# Install (or remove) the macOS launchd job that runs the daily update.
#
#   scripts/install_daily_update.sh            # install / update; runs daily at 6:30am
#   scripts/install_daily_update.sh 7 15       # ... at 7:15am instead
#   scripts/install_daily_update.sh --remove   # uninstall
#
# If the Mac is asleep at that time, launchd runs the job when it wakes; if
# it's shut down, that day is skipped and the next run looks back further.
# Output goes to logs/daily.log.
set -euo pipefail

LABEL="com.policypulse.daily-update"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="gui/$(id -u)"

if [[ "${1:-}" == "--remove" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL."
  exit 0
fi

HOUR="${1:-6}"
MINUTE="${2:-30}"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <!-- keep the Mac awake until the update finishes -->
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$ROOT/venv/bin/python</string><string>-u</string><string>-m</string><string>ingest.daily</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/logs/daily.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/daily.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin</string></dict>
</dict>
</plist>
PLIST

plutil -lint "$PLIST" >/dev/null
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
printf 'Installed %s: runs daily at %d:%02d. Log: %s/logs/daily.log\n' "$LABEL" "$HOUR" "$MINUTE" "$ROOT"
echo "Run it now with: launchctl kickstart $DOMAIN/$LABEL"
