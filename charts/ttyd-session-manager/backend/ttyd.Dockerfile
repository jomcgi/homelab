FROM alpine:3.19

# Install ttyd, git, fish, and basic dev tools
RUN apk add --no-cache \
    ttyd \
    git \
    fish \
    curl \
    wget \
    vim \
    nano \
    bash \
    ca-certificates \
    openssh-client \
    make \
    gcc \
    g++ \
    python3 \
    py3-pip \
    nodejs \
    npm

# Configure fish for better experience
RUN mkdir -p /root/.config/fish && \
    echo 'set -g fish_greeting ""' > /root/.config/fish/config.fish && \
    echo 'set -gx EDITOR vim' >> /root/.config/fish/config.fish && \
    echo 'set -gx TERM xterm-256color' >> /root/.config/fish/config.fish

WORKDIR /workspace

EXPOSE 7681

# Default command will be overridden by pod spec
CMD ["ttyd", "-p", "7681", "-W", "--writable", "fish"]
