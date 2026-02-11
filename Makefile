.PHONY: dev test lint format backend frontend all clean install dev-frontend sign dmg

install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

dev:
	cd backend && uvicorn main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -v

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

format:
	cd backend && black .
	cd backend && ruff check --fix .

backend:
	cd backend && pyinstaller --onedir --windowed \
		--add-data "models:models" \
		--add-data "../swift_tools:swift_tools" \
		main.py

frontend:
	cd frontend && npm run build

all: backend frontend
	./packaging/assemble_app.sh

clean:
	rm -rf backend/dist backend/build
	rm -rf frontend/dist
	rm -rf *.app *.dmg

sign:
	./packaging/sign_notarize.sh

dmg: all sign
	./packaging/make_dmg.sh
