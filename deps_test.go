package homelab

// This file ensures that backend dependencies are available in the root module
// for Bazel's go_deps extension. These imports are intentionally unused.

import (
	_ "github.com/gin-gonic/gin"
	_ "github.com/google/go-containerregistry/pkg/registry"
	_ "github.com/google/uuid"
	_ "github.com/gorilla/websocket"
	_ "github.com/stretchr/testify/assert"
	_ "k8s.io/metrics/pkg/client/clientset/versioned"
)
