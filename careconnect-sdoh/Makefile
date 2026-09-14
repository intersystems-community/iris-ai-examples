.PHONY: up down up-ivg test-unit test-smoke test-contract test-e2e test-ivg test-all logs clean

up:
	docker compose up -d --wait

up-ivg:
	docker compose --profile ivg up -d --wait

down:
	docker compose down -v

# Unit tests — no Docker required
# PHI guardian target 90%; agent/production coverage needs running infra (see test-ivg)
test-unit:
	python -m pytest tests/unit/ -m unit -v \
	  --cov=src/CareConnect/phi_guardian \
	  --cov-report=term-missing \
	  --cov-fail-under=90

# Smoke — containers must already be running (SKIP_DOCKER_UP=true)
test-smoke:
	SKIP_DOCKER_UP=true python -m pytest tests/e2e/ -m smoke -v

# Contract — FR acceptance
test-contract:
	SKIP_DOCKER_UP=true python -m pytest tests/e2e/ -m contract -v

# E2E — full stack
test-e2e:
	SKIP_DOCKER_UP=true python -m pytest tests/e2e/ -m e2e -v

# IVG gate round-trip — requires running IVG stack (make up-ivg)
# Primary e2e gate: 26 tests covering graph seeding, knowledge context,
# contradiction gate block/resolve/reset cycle, and Cypher API.
test-ivg:
	SKIP_DOCKER_UP=true python -m pytest tests/e2e/test_ivg_contradiction_gate.py -v

# Full suite — unit + IVG e2e (requires IVG stack running)
test-all:
	python -m pytest tests/unit/ tests/e2e/test_ivg_contradiction_gate.py \
	  -v --cov=src/CareConnect/phi_guardian --cov-report=term-missing --cov-fail-under=90

logs:
	docker compose logs -f

clean:
	docker compose down -v
	docker system prune -f
