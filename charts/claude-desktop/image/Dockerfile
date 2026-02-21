FROM debian:bookworm-slim
ARG TARGETARCH
# Release tag: v${PKG_VERSION}+claude${CLAUDE_VERSION}
# Asset name:  claude-desktop_${CLAUDE_VERSION}-${PKG_VERSION}_${arch}.deb
ARG CLAUDE_VERSION=1.1.3830
ARG PKG_VERSION=1.3.12

# Install system deps + xpra
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates wget gnupg && \
    wget -qO /usr/share/keyrings/xpra.asc https://xpra.org/xpra.asc && \
    echo "deb [signed-by=/usr/share/keyrings/xpra.asc] https://xpra.org/ bookworm main" \
      > /etc/apt/sources.list.d/xpra.list && \
    apt-get update && apt-get install -y --no-install-recommends \
      xpra xpra-x11 xpra-html5 xvfb dbus-x11 \
      xauth python3-dbus \
      libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 \
      libatspi2.0-0 libdrm2 libgbm1 libasound2 \
      fonts-liberation fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install claude-desktop .deb (separate layer for version bump caching)
RUN DEB_ARCH=$([ "$TARGETARCH" = "arm64" ] && echo "arm64" || echo "amd64") && \
    wget -qO /tmp/claude-desktop.deb \
      "https://github.com/aaddrick/claude-desktop-debian/releases/download/v${PKG_VERSION}%2Bclaude${CLAUDE_VERSION}/claude-desktop_${CLAUDE_VERSION}-${PKG_VERSION}_${DEB_ARCH}.deb" && \
    apt-get update && apt-get install -y /tmp/claude-desktop.deb && \
    rm /tmp/claude-desktop.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 user && \
    useradd -m -u 1000 -g user -s /bin/bash user && \
    mkdir -p /home/user/.config/Claude /home/user/.claude /run/user/1000 && \
    chown -R user:user /home/user /run/user/1000

ENV XDG_RUNTIME_DIR=/run/user/1000

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 14500
USER user
WORKDIR /home/user
CMD ["/app/start.sh"]
