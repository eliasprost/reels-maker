# -*- coding: utf-8 -*-
import json
import os
import re
import time

import streamlit as st
import torch
from chonkie import SemanticChunker
from loguru import logger
from TTS.api import TTS

from src.utils.media.audio import concatenate_audio_files, generate_silence
from src.utils.path import create_file_folder


class TextToSpeech:
    """
    Text-to-Speech class using Coqui TTS.
    """

    def __init__(
        self,
        model_name="tts_models/multilingual/multi-dataset/xtts_v2",
        max_length=200,
    ):
        """
        See all available models at by running `tts --list_models`

        Args:
            model_name (str, optional): Model name.
                Defaults to "tts_models/multilingual/multi-dataset/xtts_v2".
            max_length (int, optional): Maximum length of the text to be processed. Defaults to 200.
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = TTS(model_name=model_name, progress_bar=False).to(self.device)
        self.languages = json.load(open("./data/languages.json"))
        self.max_length = max_length
        self.chunker = SemanticChunker(
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            chunk_size=int(self.max_length / 5),
            min_chunk_size=int(self.max_length / 6),
            min_sentences=2,
            threshold=0.8,
        )

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

        # normalize Brazilian laughs
        result = re.sub(r"\b[kK]{4,}\b", "kkk", result)

        # note: not removing apostrophes
        regex_expr = r"\s['|’]|['|’]\s|[\^_~@!&;#:\-%—“”‘\"%\*/{}\[\]\(\)\\|<>=+]"
        result = re.sub(regex_expr, " ", result)
        result = result.replace("+", "plus").replace("&", "and")
        result = " ".join(result.split())

        return result[:-1] if result.endswith(".") else result

    def generate_audio_clip(
        self,
        text: str,
        output_path: str,
        language: str,
        speaker: str = "Abrahan Mack",
        speaker_wav: str = None,
        speed: float = 1.0,
        separator: str = None,
    ) -> None:
        """
        Generate an audio clip from text

        Args:
            text: Text to convert to speech
            output_path: Path to save the audio clip
            language: Language of the text.
            speaker: Speaker to use for the audio clip. Default is "Abrahan Mack".
            speaker_wav: Path to the speaker reference audio file.
                Default is None and the speaker is used.
            speed: Speed of the audio clip. Default is 1.0
            separator: Separator to split the text into sentences. Default is None.
                If no specified the text will be splitted using the semantic chunker

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
                    speaker=speaker if not speaker_wav else None,
                    speaker_wav=speaker_wav,
                    speed=speed,
                    split_sentences=False,
                )
                end = time.time()

                logger.info(
                    f"Audio clip generated: {output_path} in {end - start:.2f} seconds",
                )

            elif text and len(text) > 200:
                processed_files = []

                try:
                    if separator:
                        # Split the text into chunks using the separator
                        splits = text.split(separator)

                    else:
                        # Split the text into chunks using the semantic chunker
                        splits = [
                            chunk.text.strip() for chunk in self.chunker.chunk(text)
                        ]

                    # Clean empty text from splits
                    splits = [part.strip() for part in splits if part.strip() != ""]

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
                            speaker=speaker if not speaker_wav else None,
                            speaker_wav=speaker_wav,
                            speed=speed,
                            split_sentences=False,
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


tts_pipeline = TextToSpeech()


@st.cache_resource
def get_text_to_speech():
    """
    Create and cache a SpeechToText instance to use in Streamlit with cache.
    """
    return tts_pipeline
