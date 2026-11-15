# NGSH — Next-Generation Scaled Hypersonics
#
# The Makefile is the single entry point for every common task. It works with
# or without Docker: `make dev` runs the services directly with uv, and
# `make compose-up` runs the containerised topology instead.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PY ?= uv run
UV ?= uv
PYTEST := $(PY) pytest
RUFF := $(PY) ruff

DATA_DIR ?= data
export NGSH_DSN ?= sqlite:///./$(DATA_DIR)/ngsh.db
export NGSH_TENANT ?= ngsh
export NGSH_DEPLOYMENT_PROFILE ?= local

SERVICE_PORTS := ontology:8081 fabric:8082 policy:8083 audit:8084 thread:8085 ingest:8086 architecture:8088 workforce:8089 manufacturing:8090 testlab:8091 supply:8092 engagement:8093 industrial:8094 analytics:8095 integration:8096

.PHONY: help
help: ## Show the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Install dependencies and create the local environment
	$(UV) sync --all-extras
	@mkdir -p $(DATA_DIR)

.PHONY: test
test: ## Run the full test suite
	$(PYTEST)

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(PYTEST) tests/unit

.PHONY: test-integration
test-integration: ## Run integration and end-to-end tests
	$(PYTEST) tests/integration tests/e2e

.PHONY: lint
lint: ## Lint and format-check the Python code
	$(RUFF) check libs services tests
	$(RUFF) format --check libs services tests

.PHONY: format
format: ## Auto-format the Python code
	$(RUFF) format libs services tests
	$(RUFF) check --fix libs services tests

.PHONY: contracts
contracts: ## Validate the contract layer
	$(PY) tools/validate_contracts.py

.PHONY: codegen
codegen: ## Regenerate the typed models from the contract layer
	$(PY) tools/codegen/generate.py

.PHONY: codegen-check
codegen-check: ## Fail if the generated models are out of date
	$(PY) tools/codegen/generate.py --check

.PHONY: dev
dev: ## Run the foundation and the Pillar A first slice locally
	@$(PY) scripts/run_stack.py

.PHONY: dev-ontology
dev-ontology: ## Run the ontology service
	NGSH_SERVICE_NAME=ontology NGSH_PORT=8081 $(PY) -m ngsh_ontology.app

.PHONY: dev-fabric
dev-fabric: ## Run the fabric service
	NGSH_SERVICE_NAME=fabric NGSH_PORT=8082 $(PY) -m ngsh_fabric.app

.PHONY: dev-policy
dev-policy: ## Run the policy service
	NGSH_SERVICE_NAME=policy NGSH_PORT=8083 $(PY) -m ngsh_policy.app

.PHONY: dev-audit
dev-audit: ## Run the audit service
	NGSH_SERVICE_NAME=audit NGSH_PORT=8084 $(PY) -m ngsh_audit.app

.PHONY: dev-thread
dev-thread: ## Run the thread service
	NGSH_SERVICE_NAME=thread NGSH_PORT=8085 $(PY) -m ngsh_thread.app

.PHONY: dev-ingest
dev-ingest: ## Run the ingest service
	NGSH_SERVICE_NAME=ingest NGSH_PORT=8086 $(PY) -m ngsh_ingest.app

.PHONY: dev-architecture
dev-architecture: ## Run the architecture service (Pillar A first slice)
	NGSH_SERVICE_NAME=architecture NGSH_PORT=8088 $(PY) -m ngsh_architecture.app

.PHONY: dev-workforce
dev-workforce: ## Run the workforce service
	NGSH_SERVICE_NAME=workforce NGSH_PORT=8089 $(PY) -m ngsh_workforce.app

.PHONY: dev-manufacturing
dev-manufacturing: ## Run the manufacturing service
	NGSH_SERVICE_NAME=manufacturing NGSH_PORT=8090 $(PY) -m ngsh_manufacturing.app

.PHONY: dev-testlab
dev-testlab: ## Run the testlab service
	NGSH_SERVICE_NAME=testlab NGSH_PORT=8091 $(PY) -m ngsh_testlab.app

.PHONY: dev-supply
dev-supply: ## Run the supply service
	NGSH_SERVICE_NAME=supply NGSH_PORT=8092 $(PY) -m ngsh_supply.app

.PHONY: dev-engagement
dev-engagement: ## Run the engagement service
	NGSH_SERVICE_NAME=engagement NGSH_PORT=8093 $(PY) -m ngsh_engagement.app

.PHONY: dev-industrial
dev-industrial: ## Run the industrial service (Pillar H)
	NGSH_SERVICE_NAME=industrial NGSH_PORT=8094 $(PY) -m ngsh_industrial.app

.PHONY: dev-analytics
dev-analytics: ## Run the analytics service (programme KPIs)
	NGSH_SERVICE_NAME=analytics NGSH_PORT=8095 $(PY) -m ngsh_analytics.app

.PHONY: dev-integration
dev-integration: ## Run the integration service (interface register)
	NGSH_SERVICE_NAME=integration NGSH_PORT=8096 $(PY) -m ngsh_integration.app

.PHONY: demo
demo: ## Exercise the full vertical slice against the running stack
	$(PY) scripts/demo.py

.PHONY: demo-programme
demo-programme: ## Walk all six pillars in one thread against the running stack
	$(PY) scripts/demo_programme.py

.PHONY: demo-edge
demo-edge: ## Exercise the edge annex capture and reconciliation flow
	$(PY) scripts/demo_edge.py

.PHONY: dev-edge
dev-edge: ## Run the edge annex agent
	NGSH_SERVICE_NAME=edge NGSH_PORT=8087 NGSH_FABRIC_URL=http://127.0.0.1:8082 $(PY) -m ngsh_edge.app

.PHONY: seed
seed: ## Load a demonstration dataset into the fabric
	$(PY) scripts/seed.py

.PHONY: compose-up
compose-up: ## Bring up the containerised topology
	docker compose -f deploy/compose/docker-compose.yml up -d --build

.PHONY: compose-down
compose-down: ## Tear down the containerised topology
	docker compose -f deploy/compose/docker-compose.yml down -v

.PHONY: clean
clean: ## Remove local state
	rm -rf $(DATA_DIR) .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

.PHONY: verify
verify: lint contracts codegen-check test ## Run every gate
	@echo "All gates passed."
