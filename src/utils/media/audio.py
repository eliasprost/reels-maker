# -*- coding: utf-8 -*-
import os
import random
from pathlib import Path

import ffmpeg
from loguru import logger

from src.config import settings
from src.utils.path import create_file_folder


def generate_silence(duration: float, output_path: str) -> None:
    """
    Generate a silent MP3 file of given duration in seconds.

    Args:
        duration (int): Duration of silence in seconds.
        output_path (str): Path to save the silent MP
    """
    ffmpeg.input("anullsrc=r=44100:cl=stereo", f="lavfi").output(
        output_path,
        t=duration,
    ).run(overwrite_output=True)


def get_audio_duration(file_path: str) -> float:
    """
    Get the duration (in seconds) of an MP3 file using ffmpeg.

    Args:
        file_path (str): Path to the MP3 file.
    """
    probe = ffmpeg.probe(file_path)
    return float(probe["format"]["duration"])


def concatenate_audio_files(
    files: list,
    silence_duration: float = 0.2,
    output_file: str = "result.mp3",
) -> None:
    """
    Concatenates multiple MP3 files with silence between them.

    Args:
        files (list): List of MP3 files to concatenate.
        silence_duration (float): Duration of silence in seconds between each file.
        output_file (str): Name of the output file.
    """

    # check if file exists
    if os.path.exists(output_file):
        logger.info(f"Audio file already exists at: {output_file}")
        return

    # Create output folder if it doesn't exist
    create_file_folder(output_file)

    # Generate silence file
    silence_path = Path(settings.TEMP_PATH) / "silence.mp3"
    generate_silence(silence_duration, silence_path)

    # Create a list of input files alternating between audio and silence
    inputs = []
    for i, mp3 in enumerate(files):
        inputs.append(ffmpeg.input(mp3))
        if i < len(files) - 1:  # Avoid adding silence at the end
            inputs.append(ffmpeg.input(silence_path))

    # Concatenate the inputs
    try:
        ffmpeg.concat(*inputs, v=0, a=1).output(output_file).run(overwrite_output=True)
        logger.info(f"Audio files concatenated to {output_file}")
    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode('utf8')}")
        raise e
    finally:
        # Cleanup temporary silence file
        os.remove(silence_path)


def cut_audio(
    input_path: str,
    output_path: str,
    start_time: float = None,
    end_time: float = None,
    fade_duration: int = 0,
    duration: float = settings.MIN_VIDEO_DURATION,
) -> None:
    """
    Cut an MP3 audio file between start_time and end_time and apply optional fade effects.

    Args:
        input_path (str): Path to the input audio file.
        output_path (str): Path to the output audio file.
        start_time (float): Start time in seconds.
        end_time (float): End time in seconds.
        duration (float): Duration of the output audio in seconds. Default is MIN_VIDEO_DURATION.
        fade_duration (int): Duration of fade-in and fade-out effects in seconds. Put 0 to disable.
    """

    # check if file exists
    if os.path.exists(output_path):
        logger.info(f"Audio file already exists at: {output_path}")
        return

    try:
        # Create output folder if it doesn't exist
        create_file_folder(output_path)

        input_duration = int(get_audio_duration(input_path))

        if not start_time or not end_time:

            if input_duration < duration:
                start_time = 0
                end_time = input_duration
                logger.info(
                    f"Audio duration is less than {duration}s. Keeping the full audio.",
                )

            else:
                start_time = random.randint(0, int(input_duration) - int(duration))
                end_time = start_time + duration

        # To get if the audio is shorter than the duration
        output_duration = end_time - start_time

        # Start the FFmpeg processing
        filter_chain = ffmpeg.input(input_path, ss=start_time, t=output_duration)

        if fade_duration > 0:
            fade = min(
                fade_duration,
                output_duration / 5,
            )  # Fade-in/out is at most fade_duration sec or 20% of duration
            filter_chain = filter_chain.filter(
                "afade",
                type="in",
                start_time=0,
                duration=fade,
            ).filter(
                "afade",
                type="out",
                start_time=output_duration - fade,
                duration=fade,
            )

        (
            filter_chain.output(
                output_path,
                format="mp3",
                acodec="libmp3lame",
                qscale=2,
            )
            .overwrite_output()
            .run()
        )

        logger.info(
            f"""
            Audio cut between {start_time}s and {end_time}s with fade effects = {fade} at:
            - {output_path}
            """,
        )

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode('utf8')}")
        raise e
