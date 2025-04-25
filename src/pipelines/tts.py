# -*- coding: utf-8 -*-
import json
import os
import re
import tempfile
import time

import edge_tts
import ffmpeg
import streamlit as st
from loguru import logger

from src.schemas import Speaker
from src.utils.common import create_file_folder


class TextToSpeech:
    """
    Text-to-Speech class using Edge TTS.
    - https://github.com/rany2/edge-tts
    """

    def __init__(
        self,
    ):
        """
        See all available models at by running `tts --list_models`
        """
        self.languages = json.load(open("./data/languages.json"))

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

    def speedup_audio(
        self,
        input_path: str,
        speed: float,
        output_path: str = None,
    ) -> None:
        """
        Speed up an audio file using ffmpeg.

        Args:
            input_path (str): Path to the input audio file.
            speed (float): Speed factor (e.g., 1.3 for 30% faster).
            output_path (str): Path to the output audio file.
                If None, overwrite the input file safely.
        """

        def _build_atempo_chain(speed):
            filters = []
            while speed > 2.0:
                filters.append("atempo=2.0")
                speed /= 2.0
            while speed < 0.5:
                filters.append("atempo=0.5")
                speed *= 2.0
            filters.append(f"atempo={speed}")
            return ",".join(filters)

        atempo_filter = _build_atempo_chain(speed)

        if output_path is None:
            # Create temp file in the same directory as input
            input_dir = os.path.dirname(input_path) or "."
            with tempfile.NamedTemporaryFile(
                suffix=".mp3",
                dir=input_dir,
                delete=False,
            ) as tmp_file:
                temp_path = tmp_file.name

            try:
                # Process to temp file
                (
                    ffmpeg.input(input_path)
                    .output(temp_path, **{"filter:a": atempo_filter})
                    .run(overwrite_output=True)
                )

                # Replace original with temp file
                os.replace(temp_path, input_path)

            except Exception as e:
                # Clean up temp file if something went wrong
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise e

        else:
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Process directly to output path
            (
                ffmpeg.input(input_path)
                .output(output_path, **{"filter:a": atempo_filter})
                .run(overwrite_output=True)
            )

    def generate_audio_clip(
        self,
        text: str,
        output_path: str,
        speaker: Speaker,
        speed: float = 1.0,
    ) -> None:
        """
        Generate an audio clip from text

        Args:
            text: Text to convert to speech
            output_path: Path to save the audio clip
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

        start = time.time()
        try:
            sanitized_text = self.sanitize_text(text)

            if len(sanitized_text) == 0:
                logger.info("Text is empty after sanitization. Skipping generation.")

            communicate = edge_tts.Communicate(sanitized_text, speaker.name)
            communicate.save_sync(output_path)

            if speed != 1.0:
                self.speedup_audio(output_path, speed)

            end = time.time()

            logger.info(
                f"Audio clip generated: {output_path} in {end - start:.2f} s with speed {speed}.",
            )

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
