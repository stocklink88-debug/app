.PHONY: help install install-ui dev dev-api dev-ui build build-ui run test lint clean

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@echo "make install    Instala todo (backend + interfaz)"
	@echo "make run        Arranca la app en http://localhost:8000"
	@echo "make dev-api    API con recarga en caliente (:8000)"
	@echo "make dev-ui     Interfaz con recarga en caliente (:5173)"
	@echo "make test       Suite de tests del backend"
	@echo "make build      Compila la interfaz dentro del backend"

backend/.venv:
	python3 -m venv backend/.venv

install: backend/.venv install-ui
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements-dev.txt

install-ui:
	cd frontend && npm install

build-ui build:
	cd frontend && npm run build

run: build-ui
	cd backend && .venv/bin/python -m uvicorn higgsstudio.main:app --host 0.0.0.0 --port 8000

dev-api:
	cd backend && .venv/bin/python -m uvicorn higgsstudio.main:app --reload --host 0.0.0.0 --port 8000

dev-ui:
	cd frontend && npm run dev

dev:
	@echo "Abre dos terminales: 'make dev-api' y 'make dev-ui'"

test:
	cd backend && .venv/bin/python -m pytest

typecheck:
	cd frontend && npm run typecheck

clean:
	rm -rf backend/data backend/higgsstudio/static frontend/node_modules backend/.venv
