#!/bin/bash
# One-time installer for the Mac mini. In Terminal:  bash ~/Downloads/CommandCenterMac/install.sh
# Folder must contain: install.sh, mac_collect.py, deploy_key
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/CommandCenter"; CONF="$HOME/.config/command-center"; PLIST="$HOME/Library/LaunchAgents/com.commandcenter.mac.plist"
REPO="${GH_REPO:-briancapano-ctrl/command-center}"
mkdir -p "$DIR" "$CONF"
cp "$HERE/mac_collect.py" "$DIR/mac_collect.py"
if [ -f "$HERE/deploy_key" ]; then
  mv "$HERE/deploy_key" "$CONF/deploy_key"; chmod 600 "$CONF/deploy_key"
fi
[ -f "$CONF/deploy_key" ] || { echo "deploy_key missing"; exit 1; }
if [ ! -f "$CONF/env" ]; then
  read -s -p "Dashboard passphrase (the one you unlock the page with): " PW; echo
  printf "GH_REPO=%s\nCC_PASSPHRASE=%s\n" "$REPO" "$PW" > "$CONF/env"
  chmod 600 "$CONF/env"
fi
PY="$(python3 -c 'import os,sys;print(os.path.realpath(sys.executable))')"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>com.commandcenter.mac</string>
 <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/mac_collect.py</string></array>
 <key>StartInterval</key><integer>600</integer>
 <key>RunAtLoad</key><true/>
 <key>StandardOutPath</key><string>$DIR/log.txt</string>
 <key>StandardErrorPath</key><string>$DIR/log.txt</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/com.commandcenter.mac" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo
echo "Installed. One manual step: System Settings > Privacy & Security > Full Disk Access > click +, press Cmd+Shift+G, paste this path, Open:"
echo "  $PY"
echo "Then test:  launchctl kickstart -k gui/$(id -u)/com.commandcenter.mac ; sleep 15 ; cat $DIR/log.txt"
