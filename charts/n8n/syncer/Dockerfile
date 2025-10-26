# Build stage
FROM golang:1.25-alpine AS builder

WORKDIR /workspace

# Install build dependencies
RUN apk add --no-cache git ca-certificates

# Copy root go mod files (for pkg/n8n dependency)
COPY go.mod go.sum ./
COPY pkg/ ./pkg/

# Copy syncer module
COPY charts/n8n/syncer/ ./charts/n8n/syncer/

# Download dependencies from syncer directory
WORKDIR /workspace/charts/n8n/syncer
RUN go mod download

# Build the application
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags='-w -s -extldflags "-static"' \
    -a \
    -o syncer \
    .

# Final stage
FROM gcr.io/distroless/static-debian12:nonroot

# Copy CA certificates from builder
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Copy the binary
COPY --from=builder /workspace/charts/n8n/syncer/syncer /syncer

# Use non-root user
USER nonroot:nonroot

# Run the syncer
ENTRYPOINT ["/syncer"]
