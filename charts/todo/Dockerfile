FROM golang:1.23-alpine AS builder

WORKDIR /app
COPY src/go.mod ./
RUN go mod download

COPY src/*.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /todo

FROM alpine:3.21

RUN apk add --no-cache git openssh-client tzdata && \
    addgroup -g 1000 todo && \
    adduser -u 1000 -G todo -s /bin/sh -D todo && \
    mkdir -p /data /app/static && \
    chown -R todo:todo /data /app

COPY --from=builder /todo /usr/local/bin/todo
COPY --chown=todo:todo static /app/static

ENV STATIC_DIR=/app/static
ENV DATA_DIR=/data

EXPOSE 8080

USER todo
CMD ["todo"]
