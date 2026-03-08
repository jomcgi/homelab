# ruleid: no-dockerfile
FROM golang:1.25 AS builder
WORKDIR /workspace
COPY go.mod go.mod
# ruleid: no-dockerfile
FROM gcr.io/distroless/static:nonroot
COPY --from=builder /workspace/manager .
