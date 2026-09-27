.PHONY: install test lint typecheck run docker-up docker-down benchmark frontend

install:
	pip install -e ".[dev]"

test:
	pytest -m "not integration"

test-integration:
	pytest -m integration

lint:
	ruff check src tests evaluation

typecheck:
	mypy

run:
	uvicorn repomind.api.main:app --reload --port 8000

docker-up:
	docker compose up --build

docker-down:
	docker compose down

benchmark:
	python -m evaluation.benchmark --repository $(REPO) --queries evaluation/queries.example.json --output evaluation/results.json

frontend:
	cd frontend && npm install && npm run dev
