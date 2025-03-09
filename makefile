define Comment
	- Run `make install-dev` to install the project dev dependencies.
	- Run `make download` to download all the background media in one go.
	- Run `make start` to start the Streamlit app.
endef

.PHONY: install-dev download start

install-dev:
	@echo "1. Installing pre-commit"
	pre-commit install
	@echo "2. Installing unidic to use MeloTTS"
	python -m unidic download
	@echo "-- Finished --"
	@echo "Please, run `poetry shell` to refresh the virtual environment."

download:
	@echo "Downloading all background media files..."
	python scripts/download_background_media.py

start:
	@echo "Running the main.py..."
	python -m src.main
