.PHONY: generate test build clean

# Generate client from OpenAPI spec
generate:
	@echo "Generating n8n client from OpenAPI spec..."
	go generate ./...
	@echo "✓ Client generated successfully"

# Run tests
test:
	@echo "Running tests..."
	go test -v -race -coverprofile=coverage.out ./...
	@echo "✓ Tests passed"

# Build package to verify compilation
build:
	@echo "Building n8n package..."
	go build -o /tmp/n8n-build-test .
	@echo "✓ Build successful"

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	rm -f generated.go coverage.out /tmp/n8n-build-test
	@echo "✓ Cleaned"

# Verify OpenAPI spec is valid
validate:
	@echo "Validating OpenAPI spec..."
	@command -v openapi-generator-cli >/dev/null 2>&1 || { echo "openapi-generator-cli not found. Install with: npm install -g @openapitools/openapi-generator-cli"; exit 1; }
	openapi-generator-cli validate -i openapi.yaml
	@echo "✓ OpenAPI spec is valid"

# Show help
help:
	@echo "N8N Go Client - Available targets:"
	@echo ""
	@echo "  make generate   - Regenerate client from OpenAPI spec"
	@echo "  make test       - Run tests with coverage"
	@echo "  make build      - Build package to verify compilation"
	@echo "  make clean      - Remove generated files"
	@echo "  make validate   - Validate OpenAPI spec"
	@echo "  make help       - Show this help message"
