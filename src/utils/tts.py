# -*- coding: utf-8 -*-
import json
import os
import re
import subprocess
import time
from typing import List

import spacy
import streamlit as st
import torch
from loguru import logger
from TTS.api import TTS

from utils.media.audio import concatenate_audio_files, generate_silence
from utils.path import create_file_folder


class TextToSpeech:
    def __init__(self, model_name="tts_models/multilingual/multi-dataset/xtts_v2"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = TTS(model_name=model_name, progress_bar=False).to(self.device)
        self.languages = json.load(open("./data/languages.json"))

    def get_spacy_model(self, language: str) -> str:
        """
        Returns the spaCy model name for a given language code.

        Args:
            language (str): Language code for which spaCy model is required.
        """

        for lang in self.languages:
            if lang["lang_code"] == language:
                logger.info(
                    f"Using spaCy model {lang['spacy_model']} for language {language}",
                )
                return lang["spacy_model"]

        logger.error(f"Language {language} not supported. Using english model instead.")
        return "en_core_web_sm"

    def load_spacy_model(self, language: str) -> spacy.language.Language:
        """
        Load the correct Spacy model given the language.

        Args:
            language (str): Language code for which spaCy model is required.
        """

        model_name = self.get_spacy_model(language)

        try:
            logger.info(f"Loading spaCy model {model_name}")
            return spacy.load(model_name)

        except OSError:

            logger.info(f"Model {model_name} not found. Downloading...")
            subprocess.run(["python", "-m", "spacy", "download", model_name])

            logger.info(f"Loading spaCy model {model_name}")
            return spacy.load(model_name)

    def sanitize_text(self, text: str) -> str:
        """
        Sanitizes the text for text to speech.
        What gets removed:
            - following characters: ^_~@!&;#:-%“”‘"%*/{}[]()\|<>?=+
            - any http or https links

        Args:
            text (str): Text to be sanitized
        """  # noqa: W605

        # remove any urls from the text
        regex_urls = r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"  # noqa: E501

        result = re.sub(regex_urls, " ", text)

        # note: not removing apostrophes
        regex_expr = r"\s['|’]|['|’]\s|[\^_~@!&;#:\-%—“”‘\"%\*/{}\[\]\(\)\\|<>=+]"
        result = re.sub(regex_expr, " ", result)
        result = result.replace("+", "plus").replace("&", "and")
        result = " ".join(result.split())

        return result[:-1] if result.endswith(".") else result

    def split_text(self, text: str, language: str, max_length: int = 200) -> List[str]:
        """
        Split a long text into multiple shorter texts based on a maximum length and mantaining
        coherence with sentences.
        Args:
            text (str): Text to split
            language (str): Language of the text. Used to load the appropriate spaCy model.
            max_length (int): Maximum length of each chunk. Default is 200 characters.
        """

        spacy_model = self.load_spacy_model(language)
        doc = spacy_model(text)
        phrases = []

        for sent in doc.sents:
            sentence = sent.text.strip()
            if len(sentence) <= max_length:
                phrases.append(sentence)
            else:
                # Further split on commas and semicolons while keeping coherence
                parts = [part.strip() for part in sentence.split(",")]
                current_phrase = ""

                for part in parts:
                    candidate = (
                        (current_phrase + ", " + part) if current_phrase else part
                    )
                    if len(candidate) <= max_length:
                        current_phrase = candidate
                    else:
                        if current_phrase:
                            phrases.append(current_phrase.strip())
                        current_phrase = part

                if current_phrase:
                    phrases.append(current_phrase.strip())

        return phrases

    def generate_audio_clip(
        self,
        text: str,
        output_path: str,
        language: str,
        speaker: str = "Abrahan Mack",
        speed: float = 1.0,
    ) -> None:
        """
        Generate an audio clip from text

        Args:
            text: Text to convert to speech
            output_path: Path to save the audio clip
            language: Language of the text.
            speaker: Speaker to use for the audio clip. Default is "Abrahan Mack".
            speed: Speed of the audio clip. Default is 1.0

        """

        if not output_path:
            logger.info(f"output_path is invalid: {output_path}. Skipping generation.")
            return

        if os.path.exists(output_path):
            logger.info(
                f"Audio clip already exists: {output_path}. Skipping generation.",
            )
            return

        # Create the folder if it doesn't exist
        create_file_folder(output_path)

        folder_path = os.path.dirname(output_path)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            logger.info(f"Folder not found. Created folder: {folder_path}")

        try:
            if text and len(text) <= 200:
                sanitized_text = self.sanitize_text(text)
                start = time.time()
                self.model.tts_to_file(
                    text=sanitized_text,
                    language=language,
                    file_path=output_path,
                    speaker=speaker,
                    speed=speed,
                )
                end = time.time()

                logger.info(
                    f"Audio clip generated: {output_path} in {end - start:.2f} seconds",
                )

            elif text and len(text) > 200:
                processed_files = []

                try:
                    splits = self.split_text(text, language)

                    # Clean empty text from splits
                    splits = [part for part in splits if part.strip() != ""]

                    # Get the file extension to mantain in the splits output path
                    _, extension = os.path.splitext(output_path)
                    temp_folder = ".temp"
                    if not os.path.exists(folder_path):
                        os.makedirs(folder_path, exist_ok=True)
                        logger.info(f"Folder not found. Created folder: {folder_path}")

                    for idx, text in enumerate(splits):

                        sanitized_text = self.sanitize_text(text)
                        start = time.time()
                        self.model.tts_to_file(
                            text=sanitized_text,
                            language=language,
                            file_path=os.path.join(
                                temp_folder,
                                f"_temp_split_{idx}{extension}",
                            ),
                            speaker=speaker,
                            speed=speed,
                        )
                        end = time.time()
                        processed_files.append(
                            os.path.join(temp_folder, f"_temp_split_{idx}{extension}"),
                        )

                    concatenate_audio_files(
                        files=processed_files,
                        output_file=output_path,
                    )

                except Exception as e:
                    raise e

                finally:
                    for file in processed_files:
                        os.remove(file)

            else:
                logger.warning("Text is empty. Generating silence.")
                generate_silence(duration=1, output_path=output_path)

        except Exception as e:
            logger.error(f"Error generating audio clip with the following text: {text}")
            logger.error(f"Error generating audio clip: {e}")
            raise (e)


@st.cache_resource
def get_text_to_speech():
    """
    Create and cache a SpeechToText instance.
    """
    return TextToSpeech()
