.PHONY: help fmt lint test compile promote run clean install

help: ## Show this help message
	@echo "Lacuna v2 - Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and pre-commit hooks
	uv sync --all-extras --dev
	uv run pre-commit install

fmt: ## Format code with ruff and black
	uv run ruff check --fix .
	uv run ruff format .
	#uv run black .

lint: ## Type check with mypy
	uv run mypy packages/ tools/

test: ## Run pytest with coverage
	uv run pytest -v --cov

compile: ## Validate and compile example config (no reload)
	uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only

promote: ## Compile and promote config (with reload)
	uv run lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config

run: ## Run with docker compose
	docker compose -f infra/compose.yaml up --build

clean: ## Remove cache and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf dist build
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete

.DEFAULT_GOAL := help
