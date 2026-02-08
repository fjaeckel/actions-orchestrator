.PHONY: help install setup start stop status unregister destroy clean

PYTHON ?= python3
CONFIG ?= config.yaml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	$(PYTHON) -m pip install -r requirements.txt

setup: ## Download runner + configure all repos (no start)
	$(PYTHON) -m orchestrator -c $(CONFIG) setup

start: ## Start all runners and monitor (blocks until Ctrl+C)
	$(PYTHON) -m orchestrator -c $(CONFIG) start

stop: ## Stop all running runners
	$(PYTHON) -m orchestrator -c $(CONFIG) stop

status: ## Show runner status from GitHub API
	$(PYTHON) -m orchestrator -c $(CONFIG) status

unregister: ## Unregister all runners from GitHub
	$(PYTHON) -m orchestrator -c $(CONFIG) unregister

destroy: ## Unregister + delete all runner directories
	$(PYTHON) -m orchestrator -c $(CONFIG) destroy

clean: ## Remove runner template and logs
	rm -rf _runner_template runners/ *.log
