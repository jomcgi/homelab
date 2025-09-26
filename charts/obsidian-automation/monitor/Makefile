# Makefile for Obsidian Sync Monitor

# Variables
BINARY_NAME := sync-monitor
IMAGE_NAME := ghcr.io/jomcgi/obsidian-automation-sync-monitor
IMAGE_TAG := latest
GO_VERSION := 1.24

# Go parameters
GOCMD := go
GOBUILD := $(GOCMD) build
GOCLEAN := $(GOCMD) clean
GOTEST := $(GOCMD) test
GOGET := $(GOCMD) get
GOMOD := $(GOCMD) mod

# Build parameters
BUILD_DIR := ./build
LDFLAGS := -ldflags="-w -s"

.PHONY: all build clean test deps lint docker-build docker-push help

## Build the binary
build:
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 $(GOBUILD) $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME) main.go

## Clean build artifacts
clean:
	$(GOCLEAN)
	rm -rf $(BUILD_DIR)

## Run tests
test:
	$(GOTEST) -v ./...

## Run tests with coverage
test-coverage:
	$(GOTEST) -v -coverprofile=coverage.out ./...
	$(GOCMD) tool cover -html=coverage.out -o coverage.html

## Download dependencies
deps:
	$(GOMOD) download
	$(GOMOD) tidy

## Run linter
lint:
	golangci-lint run

## Build Docker image
docker-build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

## Push Docker image
docker-push: docker-build
	docker push $(IMAGE_NAME):$(IMAGE_TAG)

## Build multi-arch Docker images
docker-buildx:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG) --push .

## Run the application locally
run:
	$(GOBUILD) -o $(BUILD_DIR)/$(BINARY_NAME) main.go
	$(BUILD_DIR)/$(BINARY_NAME) --log-level=debug

## Format Go code
fmt:
	$(GOCMD) fmt ./...

## Update Go modules
mod-update:
	$(GOMOD) get -u ./...
	$(GOMOD) tidy

## Generate documentation
docs:
	$(GOCMD) doc -all ./...

## Install development tools
install-tools:
	$(GOGET) github.com/golangci/golangci-lint/cmd/golangci-lint@latest

## Show help
help:
	@echo 'Management commands for Obsidian Sync Monitor:'
	@echo ''
	@echo 'Usage:'
	@echo '  make build           Build the application binary'
	@echo '  make clean           Clean build artifacts'
	@echo '  make test            Run tests'
	@echo '  make test-coverage   Run tests with coverage report'
	@echo '  make deps            Download dependencies'
	@echo '  make lint            Run linter'
	@echo '  make docker-build    Build Docker image'
	@echo '  make docker-push     Build and push Docker image'
	@echo '  make docker-buildx   Build multi-arch Docker images'
	@echo '  make run             Run the application locally'
	@echo '  make fmt             Format Go code'
	@echo '  make mod-update      Update Go modules'
	@echo '  make docs            Generate documentation'
	@echo '  make install-tools   Install development tools'
	@echo '  make help            Show this help message'
	@echo ''

# Default target
all: deps lint test build