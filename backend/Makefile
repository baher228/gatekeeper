.PHONY: migrate seed dev test eval
PYTHON ?= .venv/bin/python

migrate:
	$(PYTHON) -m app.db migrate

seed:
	$(PYTHON) -m app.seed

dev:
	$(PYTHON) -m uvicorn app.main:app --reload --port 8000

test:
	DISABLE_SCHEDULER=1 $(PYTHON) -m pytest -q

eval:
	$(PYTHON) -m app.eval
