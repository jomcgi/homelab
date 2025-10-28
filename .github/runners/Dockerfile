# Custom GitHub Actions Runner with build tools for Bazel
# Based on official actions-runner image

FROM ghcr.io/actions/actions-runner:latest

# Switch to root to install packages
USER root

# Install C/C++ build tools required by Bazel
RUN apt-get update && \
    apt-get install -y \
        build-essential \
        gcc \
        g++ \
        make \
        pkg-config \
        zip \
        unzip \
        git \
        curl \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Switch back to runner user for security
USER runner
