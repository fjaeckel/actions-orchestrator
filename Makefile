.PHONY: help bootstrap install setup start stop status unregister destroy clean lint

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
CONFIG ?= config.yaml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

$(VENV_DIR)/bin/activate:
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip

bootstrap: $(VENV_DIR)/bin/activate ## Create venv and install dependencies
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "  ✓ Virtual environment ready at $(VENV_DIR)"
	@echo "  Next steps:"
	@echo "    1. cp config.yaml.example config.yaml"
	@echo "    2. Edit config.yaml with your GitHub PAT and repos"
	@echo "    3. make setup"
	@echo "    4. make start"

install: $(VENV_DIR)/bin/activate ## Install Python dependencies into venv
	$(PIP) install -r requirements.txt

setup: $(VENV_DIR)/bin/activate ## Download runner + configure all repos (no start)
	$(PYTHON) -m orchestrator -c $(CONFIG) setup

start: $(VENV_DIR)/bin/activate ## Start all runners and monitor (blocks until Ctrl+C)
	$(PYTHON) -m orchestrator -c $(CONFIG) start

stop: $(VENV_DIR)/bin/activate ## Stop all running runners
	$(PYTHON) -m orchestrator -c $(CONFIG) stop

status: $(VENV_DIR)/bin/activate ## Show runner status from GitHub API
	$(PYTHON) -m orchestrator -c $(CONFIG) status

unregister: $(VENV_DIR)/bin/activate ## Unregister all runners from GitHub
	$(PYTHON) -m orchestrator -c $(CONFIG) unregister

destroy: $(VENV_DIR)/bin/activate ## Unregister + delete all runner directories
	$(PYTHON) -m orchestrator -c $(CONFIG) destroy

clean: ## Remove runner template, logs, and venv
	rm -rf _runner_template runners/ $(VENV_DIR) *.log

lint: $(VENV_DIR)/bin/activate ## Run all linters (ruff + mypy)
	$(PIP) install -q ruff mypy types-requests types-PyYAML
	$(VENV_DIR)/bin/ruff check orchestrator/
	$(VENV_DIR)/bin/ruff format --check orchestrator/
	$(VENV_DIR)/bin/mypy orchestrator/
