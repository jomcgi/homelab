#!/bin/bash
set -e
exec xpra start \
	--bind-tcp=0.0.0.0:14500 \
	--html=on \
	--daemon=no \
	--start-child="claude-desktop --no-sandbox --disable-gpu --disable-dev-shm-usage" \
	--exit-with-children=yes \
	--no-pulseaudio \
	--no-notifications \
	--no-bell \
	--xvfb="Xvfb +extension Composite -screen 0 1920x1080x24+32 -nolisten tcp -noreset" \
	--no-mdns
