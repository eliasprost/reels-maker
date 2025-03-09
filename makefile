define Comment
	- Run `make install` to install the project.
	- Run `make download` to download all the background media in one go.
	- Run `make start` to start the Streamlit app.
endef

.PHONY: install download start

install:
	@echo "1. Installing pre-commit"
	pre-commit install
	@echo "2. Installing MeloTTS"
	cd MeloTTS
	pip install -e .
	python -m unidic download
	cd ..
	@echo "-- Finished --"
	@echo "Please, run `poetry shell` to refresh the virtual environment."

download:
	@echo "Downloading all background media files..."
	python scripts/download_background_media.py

start:
	@echo "Starting the Streamlit app..."
	streamlit run src/app.py
