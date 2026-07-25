.PHONY: up down logs health ingest test

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
