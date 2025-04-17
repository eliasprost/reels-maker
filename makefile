define Comment
	- Run `make install-dev` to install the project dev dependencies.
	- Run `make download` to download all the background media in one go.
	- Run `make start` to start the main script.
	- Run `make app` to start the Streamlit app.
endef

.PHONY: install-dev
install-dev:
	@echo "1. Installing pre-commit"
	pre-commit install
	@echo "2. Installing unidic to use MeloTTS"
	python -m unidic download
	@echo "-- Finished --"
	@echo "Please, run `'source .venv/bin/activate'` to refresh the virtual environment."

.PHONY: start
start:
	@echo "Running the main script using UV"
	uv run python3 -m src.main

.PHONY: download
download:
	@echo "Downloading all background media files..."
	python -m scripts.download_background_media

.PHONY: app
app:
	@echo "Running the Streamlit app..."
	streamlit run src/app.py
