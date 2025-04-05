# -*- coding: utf-8 -*-
import os
from typing import Any, Dict

import pysubs2
import streamlit as st
import whisper
from loguru import logger
from whisper.utils import get_writer

from src.utils.path import create_file_folder


class SpeechToText:
    """
    Speech-to-Text class using Whisper.
    """

    def __init__(self, model_name: str = "large-v3-turbo"):
        """
        See all available models at:
        - https://github.com/openai/whisper/blob/main/model-card.md#model-details
        """
        self.model = whisper.load_model(model_name)

    def transcribe_audio(self, input_file: str, language: str = "es") -> Dict[str, Any]:
        """
        Generate a transcription segments from an audio/video file.

        Args:
            input_file: Path to the audio/video file.
            language: Language of the audio. Default is "es".
        """

        str_name = input_file.split(".")[0] + ".srt"

        if os.path.exists(str_name):
            logger.info(f"Transcription already exists in {str_name}, skipping...")
            return

        try:
            segments = self.model.transcribe(input_file, fp16=False, language=language)
            logger.info(f"Transcription segments generated: {len(segments)}")
            return segments

        except Exception as e:
            logger.error(f"Error generating transcription segments: {e}")

    def generate_srt_file(
        self,
        segments: Dict[str, Any],
        input_file: str,
        output_directory: str = "./",
    ) -> None:
        """
        Generate a SRT file from transcription segments. The resulting SRT file will be saved in the
        output_directory. The name will be the same as the input but with .srt extension.

        Args:
            segments: Transcription segments
            input_file: Path to the audio/video file
            output_directory: Directory to save the SRT file. Default is "./"
        """

        # Check if exists
        create_file_folder(output_directory)

        # replace extension with .srt
        srt_filename = os.path.splitext(os.path.basename(input_file))[0] + ".srt"
        if os.path.exists(os.path.join(output_directory, srt_filename)):
            logger.info(
                f"File {srt_filename} already exists in {output_directory}, skipping...",
            )
            return

        try:
            sub_writer = get_writer("srt", output_directory)
            sub_writer(segments, input_file)

            logger.info(f"SRT file generated: {output_directory}")

        except Exception as e:
            logger.error(f"Error generating SRT file: {e}")

    def srt_to_ass(
        self,
        input_file: str,
        output_file=None,
        config: Dict[str, Any] = None,
        delete_srt=False,
    ) -> None:
        """
        Converts an SRT file to ASS, including the settings included in config.

        Args:
            input_file: Path to the SRT file.
            output_file: Path to the output ASS file. If not provided, it will be generated in the
                same directory as input_file.
            config: Configuration dict for ASS v4 Styles+. For more information:
                http://www.tcax.org/docs/ass-specs.htm
            delete_srt: Whether to delete the SRT file after conversion. Default is False.
        """

        if not output_file:
            output_file = input_file.replace(".srt", ".ass")

        subs = pysubs2.load(input_file, format="srt")

        # Customize subtitle style
        subs.styles["Default"].fontname = "Arial"
        subs.styles["Default"].fontsize = 12
        subs.styles["Default"].primarycolor = pysubs2.Color(255, 255, 255)  # White text
        subs.styles["Default"].outlinecolor = pysubs2.Color(0, 0, 0)  # Black outline
        subs.styles["Default"].backcolor = pysubs2.Color(
            0,
            0,
            0,
            128,
        )  # Semi-transparent background
        subs.styles["Default"].bold = True
        subs.styles["Default"].outline = 1  # Outline thickness
        subs.styles["Default"].shadow = 1  # Shadow depth
        subs.styles["Default"].alignment = 2  # Centered at the bottom
        subs.styles["Default"].marginv = (
            40  # Vertical Left Margin in pixels. For fine tune vertical position.
        )

        if config:
            subs.styles["Default"].update(config)

        # Save sub as ASS
        subs.save(output_file, format="ass")
        logger.info(f"SRT file converted to ASS in: {output_file}")

        if delete_srt:
            os.remove(input_file)
            logger.info(f"SRT file was removed from your disk:{input_file}")


@st.cache_resource
def get_speech_to_text():
    """
    Create and cache a SpeechToText instance.
    """
    return SpeechToText()
