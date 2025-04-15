# -*- coding: utf-8 -*-

import ssl

import pysubs2
import stable_whisper
import streamlit as st
from loguru import logger

from src.schemas import CaptionStyle


class SpeechToText:
    """
    Speech-to-Text class using Stable Ts to align audio with text.
    More info: https://github.com/jianfch/stable-ts
    """

    def __init__(self, model_name: str = "large-v3-turbo"):
        """
        See all available models at:
        - https://github.com/openai/whisper/blob/main/model-card.md#model-details
        """

        ssl._create_default_https_context = ssl._create_unverified_context
        print("HTTPS context has been updated to unverified.")

        self.model = stable_whisper.load_model(model_name)

    def generate_captions(
        self,
        input_file: str,
        text: str,
        language: str,
        output_file: str,
        style: CaptionStyle = None,
    ) -> None:
        """
        Generate captions aligning the audio with the text provided.

        Args:
            input_file (str): Path to the audio/video file.
            text (str): Text to align with the audio.
            language (str): Language of the text.
            output_file (str): Path to save the generated captions.
            style (CaptionStyle): Style to apply to the captions.
        """

        # Use default style if none is provided
        if not style:
            style = CaptionStyle()

        # Generate raw captions
        raw_caps = self.model.align(input_file, text, language=language)
        raw_caps.to_ass(
            output_file,
            segment_level=style.segment_level,
            word_level=style.word_levels,
        )

        # Apply style
        caps = pysubs2.load(output_file, format="ass")

        for property, value in style:
            # Filter out invalid pysub2 properties
            if "_" in property:
                continue
            setattr(caps.styles["Default"], property, value)

        caps.save(output_file, format="ass")
        logger.info(f"Captions generated in: {output_file}")


stt_pipeline = SpeechToText()


@st.cache_resource
def get_speech_to_text():
    """
    Create and cache a SpeechToText instance to use in Streamlit with cache
    """
    return stt_pipeline
