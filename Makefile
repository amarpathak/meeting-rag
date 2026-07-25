.PHONY: up down logs health ingest test eval

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

health:
	curl -s localhost:8000/health | python3 -m json.tool

test:
	docker compose exec api pytest -q

eval:
	docker compose exec api python -m evals.run
