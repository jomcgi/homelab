.PHONY: generate-models
generate-models:
	@echo "Generating Pydantic models from OpenAPI schema..."
	.venv/bin/datamodel-codegen \
		--input schema/obsidian-openapi.yaml \
		--output app/models/generated.py \
		--input-file-type openapi \
		--output-model-type pydantic_v2.BaseModel \
		--field-constraints \
		--use-standard-collections \
		--use-annotated \
		--target-python-version 3.11 \
		--snake-case-field \
		--collapse-root-models \
		--disable-timestamp
	@echo "Adding header to generated file..."
	@echo '# Generated from schema/obsidian-openapi.yaml - DO NOT EDIT MANUALLY\n# Run "make generate-models" to regenerate\n' | cat - app/models/generated.py > app/models/generated.py.tmp
	@mv app/models/generated.py.tmp app/models/generated.py
	@echo "Formatting generated code..."
	.venv/bin/ruff format app/models/generated.py
	@echo "Done! Generated models written to app/models/generated.py"

.PHONY: format
format:
	.venv/bin/ruff format app/

.PHONY: lint
lint:
	.venv/bin/ruff check app/

.PHONY: typecheck
typecheck:
	.venv/bin/pyright app/

.PHONY: check
check: lint typecheck
	@echo "✅ All checks passed!"

.PHONY: test
test:
	.venv/bin/pytest

.PHONY: test-cov
test-cov:
	.venv/bin/pytest --cov=app tests/

.PHONY: pre-commit-install
pre-commit-install:
	.venv/bin/pre-commit install

.PHONY: pre-commit-run
pre-commit-run:
	.venv/bin/pre-commit run --all-files

.PHONY: dev
dev:
	.venv/bin/uvicorn app.main:app --reload --port 8080

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  generate-models     - Generate Pydantic models from OpenAPI schema"
	@echo "  format              - Format code with ruff"
	@echo "  lint                - Lint code with ruff"
	@echo "  typecheck           - Type check with pyright"
	@echo "  check               - Run lint + typecheck"
	@echo "  test                - Run tests"
	@echo "  test-cov            - Run tests with coverage"
	@echo "  pre-commit-install  - Install pre-commit hooks"
	@echo "  pre-commit-run      - Run pre-commit on all files"
	@echo "  dev                 - Run development server"
