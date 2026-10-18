.PHONY: help up down seed demo test smoke api web dev clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

help:
	@echo "LedgerGraph — Operational Commands:"
	@echo "  make up       Start FalkorDB & Redis containers"
	@echo "  make down     Stop containers"
	@echo "  make seed     Seed database with demo firm & tenants"
	@echo "  make demo     Reset and re-seed database for 2-minute demo"
	@echo "  make test     Run full automated test suite (30+ tests)"
	@echo "  make smoke    Execute production smoke test script"
	@echo "  make api      Run FastAPI backend on http://localhost:8000"
	@echo "  make web      Run Next.js frontend on http://localhost:3000"
	@echo "  make clean    Remove python cache and test artifacts"

up:
	docker compose up -d falkordb

down:
	docker compose down

seed:
	PYTHONPATH=api $(PYTHON) -m app.seed

demo:
	PYTHONPATH=api $(PYTHON) -m app.seed --reset

test:
	PYTHONPATH=api $(PYTEST) api/tests/ -v

smoke:
	./scripts/smoke.sh

api:
	cd api && PYTHONPATH=. ../$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

web:
	cd web && npm run dev

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf web/.next
