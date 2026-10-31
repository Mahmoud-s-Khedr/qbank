WORKER_PROCESSES ?= 4
WORKER_THREADS ?= 4

.PHONY: infra-up infra-down be-install be-lint be-fmt be-types be-test be-test-unit be-migrate be-openapi fe-install fe-lint fe-types fe-test fe-build api-gen contract-check lint-actions pre-commit-install check be-dev be-worker eval
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
	pnpm -C frontend install --frozen-lockfile
fe-lint:
	pnpm -C frontend lint
fe-types:
	pnpm -C frontend typecheck
fe-test:
	pnpm -C frontend test:coverage
fe-build:
	pnpm -C frontend build
api-gen: be-openapi
	@if [ -d frontend ]; then pnpm -C frontend api:gen; fi
contract-check:
	$(MAKE) api-gen
	git diff --exit-code -- backend/openapi.json frontend/src/api/schema.d.ts
lint-actions:
	docker run --rm -v "$(CURDIR):/repo" -w /repo rhysd/actionlint
pre-commit-install:
	pre-commit install --install-hooks
	pre-commit install --hook-type pre-push
check: be-lint be-types be-test contract-check lint-actions
	@if [ -f frontend/package.json ]; then $(MAKE) fe-lint fe-types fe-test fe-build && pnpm -C frontend format:check; fi
be-dev:
	uv run --directory backend uvicorn qbank.api.main:app --reload
be-worker:
	uv run --directory backend dramatiq qbank.worker --processes $(WORKER_PROCESSES) --threads $(WORKER_THREADS)
eval:
	uv run --directory backend qbank-eval --models "$(MODELS)" --max-cost "$(MAX_COST)" $(if $(PAGES),--pages "$(PAGES)",) $(if $(REPEAT),--repeat "$(REPEAT)",) $(if $(OUT),--out "$(OUT)",) $(if $(DRY_RUN),--dry-run,) $(EVAL_ARGS)
