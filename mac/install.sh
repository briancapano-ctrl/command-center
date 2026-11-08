#!/bin/bash
# One-time installer for the Mac mini. Run:  bash install.sh
set -e
DIR="$HOME/CommandCenter"; CONF="$HOME/.config/command-center"; PLIST="$HOME/Library/LaunchAgents/com.commandcenter.mac.plist"
mkdir -p "$DIR" "$CONF"
cp "$(dirname "$0")/mac_collect.py" "$DIR/mac_collect.py"
PY="$(python3 -c 'import os,sys;print(os.path.realpath(sys.executable))')"
if [ ! -f "$CONF/env" ]; then
  read -p "GitHub repo (owner/name): " REPO
  read -s -p "GitHub token (fine-grained, Contents read/write on that repo): " TOK; echo
  read -s -p "Passphrase (same one you will use to unlock the page): " PW; echo
  printf "GH_REPO=%s\nGH_TOKEN=%s\nCC_PASSPHRASE=%s\n" "$REPO" "$TOK" "$PW" > "$CONF/env"
  chmod 600 "$CONF/env"
fi
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
echo "Installed. One manual step: System Settings > Privacy & Security > Full Disk Access > add this file:"
echo "  $PY"
echo "Then test:  launchctl kickstart -k gui/$(id -u)/com.commandcenter.mac ; sleep 5 ; cat $DIR/log.txt"
