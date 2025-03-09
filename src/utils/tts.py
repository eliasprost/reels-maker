# -*- coding: utf-8 -*-
import os
import re
import time

from loguru import logger
from melo.api import TTS


class TextToSpeech:
    def __init__(self, language: str = "ES", device: str = "cpu"):
        self.model = TTS(language=language, device=device)
        self.speaker_ids = self.model.hps.data.spk2id

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
        regex_urls = r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"

        result = re.sub(regex_urls, " ", text)

        # note: not removing apostrophes
        regex_expr = r"\s['|’]|['|’]\s|[\^_~@!&;#:\-%—“”‘\"%\*/{}\[\]\(\)\\|<>=+]"
        result = re.sub(regex_expr, " ", result)
        result = result.replace("+", "plus").replace("&", "and")

        # remove extra whitespace
        return " ".join(result.split())

    def generate_audio_clip(
        self,
        text: str,
        output_path: str,
        speed: float = 1.0,
    ) -> None:
        """
        Generate an audio clip from text

        Args:
            text: Text to convert to speech
            output_path: Path to save the audio clip
            speed: Speed of the audio clip. Default is 1.0
        """

        if os.path.exists(output_path):
            logger.info(
                f"Audio clip already exists: {output_path}. Skipping generation.",
            )
            return

        folder_path = os.path.dirname(output_path)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            logger.info(f"Folder not found. Created folder: {folder_path}")

        try:
            sanitized_text = self.sanitize_text(text)
            start = time.time()
            self.model.tts_to_file(
                sanitized_text,
                self.speaker_ids["ES"],
                output_path,
                speed=speed,
            )
            end = time.time()
            logger.info(
                f"Audio clip generated: {output_path} in {end - start:.2f} seconds",
            )

        except Exception as e:
            logger.error(f"Error generating audio clip: {e}")
            raise e


text_to_speech = TextToSpeech()
