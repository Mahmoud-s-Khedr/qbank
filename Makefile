.PHONY: infra-up infra-down be-install be-lint be-fmt be-types be-test be-test-unit be-migrate be-openapi fe-install fe-lint fe-types fe-test fe-build api-gen check
infra-up:
	docker compose up -d --wait postgres redis minio
	docker compose run --rm minio-init
infra-down:
	docker compose down
be-install:
	uv sync --directory backend --frozen
be-lint:
	uv run --directory backend ruff check .
	uv run --directory backend ruff format --check .
be-fmt:
	uv run --directory backend ruff format .
be-types:
	uv run --directory backend mypy
be-test:
	uv run --directory backend pytest
be-test-unit:
	uv run --directory backend pytest -m 'not integration'
be-migrate:
	uv run --directory backend alembic -c alembic.ini upgrade head
be-openapi:
	uv run --directory backend python -m qbank.api.openapi_dump
fe-install:
	pnpm -C frontend install
fe-lint:
	pnpm -C frontend lint
fe-types:
	pnpm -C frontend typecheck
fe-test:
	pnpm -C frontend test
fe-build:
	pnpm -C frontend build
api-gen: be-openapi
	@if [ -d frontend ]; then pnpm -C frontend api:gen; fi
check: be-lint be-types be-test
	@if [ -f frontend/package.json ]; then $(MAKE) fe-lint fe-types fe-test fe-build; fi
