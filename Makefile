.PHONY: setup seed dev demo api web test lint build clean
setup:
	cd apps/api && uv sync --locked --extra dev
	cd apps/web && pnpm install --frozen-lockfile
seed:
	python3 scripts/seed_demo.py
	cd apps/api && PYTHONPATH=src .venv/bin/python ../../scripts/load_demo.py
api:
	cd apps/api && PYTHONPATH=src uv run uvicorn outcomemeter.main:app --reload --host 127.0.0.1 --port 8000
web:
	cd apps/web && pnpm run dev
dev:
	./scripts/dev.sh
demo: setup seed dev
test:
	cd apps/api && uv run pytest
	cd apps/web && pnpm test
lint:
	cd apps/api && uv run ruff check src tests ../../scripts
	cd apps/api && uv run ruff format --check src tests ../../scripts
build:
	cd apps/web && pnpm run build
clean:
	rm -rf apps/api/.venv apps/web/node_modules apps/web/dist data
