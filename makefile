define Comment
	- Run `make install` to install the project.
	- Run `make start` to start the Streamlit app.
endef

.PHONY: install start

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

start:
	@echo "Starting the Streamlit app..."
	streamlit run src/app.py
