# TokenOpt development tasks (mirrors the CI pipeline in .github/workflows/ci.yml).
# Windows users without `make` can run the underlying commands directly.

PYTHON ?= python
PACKAGE = tokenopt

.PHONY: help install dev lint typecheck test coverage build audit smoke clean

help: ## Show available targets
	@echo "TokenOpt development targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F ':.*?## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install core package (editable)
	$(PYTHON) -m pip install -e .

dev: ## Install core + dev extras (pytest, ruff, mypy, pip-audit)
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Run ruff
	ruff check $(PACKAGE) tests

typecheck: ## Run mypy
	mypy $(PACKAGE)

test: ## Run pytest (includes coverage gate >= 80%)
	pytest tests/ -q

coverage: ## Run pytest with coverage report
	pytest tests/ --cov-report=term-missing

build: ## Build sdist + wheel
	$(PYTHON) -m build

audit: ## Scan runtime dependencies for known vulnerabilities
	pip-audit --path . --desc

smoke: build ## Install the wheel in a fresh venv and import it
	$(PYTHON) -m venv /tmp/tokenopt-smoke
	/tmp/tokenopt-smoke/bin/pip install --quiet dist/*.whl
	/tmp/tokenopt-smoke/bin/python -c "import $(PACKAGE); print('smoke ok:', $(PACKAGE).__version__)"

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
