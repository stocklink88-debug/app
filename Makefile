.PHONY: help install models dev-api dev-ui build run test test-slow clean docker

help:
	@echo "make install    Instala dependencias de backend y frontend"
	@echo "make models     Descarga el modelo de detección de caras"
	@echo "make dev-api    Arranca la API en modo desarrollo (:8000)"
	@echo "make dev-ui     Arranca el frontend en modo desarrollo (:5173)"
	@echo "make build      Compila el frontend dentro del backend"
	@echo "make run        Arranca todo en un único servidor (:8000)"
	@echo "make test       Tests rápidos"
	@echo "make test-slow  Tests que renderizan vídeo de verdad"
	@echo "make docker     Levanta la app con Docker Compose"

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r backend/requirements-dev.txt
	cd frontend && npm install
	$(MAKE) models

models:
	.venv/bin/python backend/scripts/fetch_models.py

dev-api:
	cd backend && ../.venv/bin/python -m uvicorn viralclips.main:app --reload --port 8000

dev-ui:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

run: build
	cd backend && ../.venv/bin/python -m uvicorn viralclips.main:app --host 0.0.0.0 --port 8000

test:
	cd backend && ../.venv/bin/python -m pytest -q -m "not slow"

test-slow:
	cd backend && ../.venv/bin/python -m pytest -q -m slow

clean:
	rm -rf backend/data backend/viralclips/static frontend/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

docker:
	docker compose up --build
