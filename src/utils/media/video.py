# -*- coding: utf-8 -*-
import os
import random
from typing import List, Literal

import ffmpeg
from loguru import logger

from src.config import settings
from src.utils.media.audio import get_audio_duration


def get_video_duration(file_path: str) -> float:
    """
    Returns the duration of a video file in seconds.

    Args:
        file_path (str): Path to the video file.
    """
    probe = ffmpeg.probe(file_path)
    return float(probe["format"]["duration"])


def create_image_videoclip(
    image_path: str,
    audio_path: str,
    output_path: str,
    preset: Literal["veryslow", "slow", "medium", "fast", "veryfast"] = settings.PRESET,
) -> None:
    """
    Combine an image and audio into an MP4 video.

    Args:
        image_path (str): Path to the image file.
        audio_path (str): Path to the audio file.
        output_path (str): Path to save the output video.
        preset (literal["veryslow", "slow", "medium", "fast", "veryfast"]): Encoding preset.
            Default is "slow".
    """

    # Check if the video already exists
    if os.path.exists(output_path):
        logger.info(f"Video already exists at: {output_path}")
        return

    try:
        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        input_image = ffmpeg.input(image_path, loop=1, framerate=60)
        input_audio = ffmpeg.input(audio_path)

        output_args = {
            "c:v": "h264_videotoolbox" if settings.USE_GPU else "libx264",
            "c:a": "aac",
            "t": get_audio_duration(audio_path),
            "pix_fmt": "yuv420p",
            "preset": preset,
            "crf": 18,
            "b:v": "5000k" if settings.USE_GPU else "3000k",
            "b:a": "256k",
        }
        (
            ffmpeg.output(input_image, input_audio, output_path, **output_args)
            .overwrite_output()
            .run()
        )

        logger.info(f"Video created at: {output_path}")

    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error: {e.stderr.decode('utf8')}")


def concatenate_videos(
    video_paths: List[str],
    output_path: str,
    preset: Literal["veryslow", "slow", "medium", "fast", "veryfast"] = settings.PRESET,
) -> None:
    """
    Concatenate videos while normalizing only the audio (leaving video untouched).

    Each video's audio is resampled to 48kHz and normalized using the loudnorm filter.
    The video stream is copied without modification. The temporary files are then concatenated
    using FFmpeg's concat demuxer.

    Args:
        video_paths (List[str]): List of video file paths to concatenate.
        output_path (str): Path to save the resulting concatenated video.
        preset (literal["veryslow", "slow", "medium", "fast", "veryfast"]):
            Encoding preset for audio processing.
    """

    if os.path.exists(output_path):
        logger.info(f"Video already exists at: {output_path}")
        return

    temp_paths = []
    list_file = "concat_list.txt"
    try:
        # Step 1: Process each video by normalizing only the audio and copying the video stream
        for idx, path in enumerate(video_paths):
            temp_output = f"temp_normalized_{idx}.mp4"
            stream = ffmpeg.input(path)
            # Leave video unchanged by copying it
            video_stream = stream.video
            # Normalize audio: resample to 48kHz and apply loudness normalization
            audio_stream = stream.audio.filter("aresample", 48000).filter(
                "loudnorm",
                i=-16,
                tp=-1.5,
                LRA=11,
            )
            ffmpeg.output(
                video_stream,
                audio_stream,
                temp_output,
                **{
                    "vcodec": "h264_videotoolbox" if settings.USE_GPU else "libx264",
                    "c:v": "copy",
                    "acodec": "aac",
                    "crf": 18,
                    "b:v": "5000k" if settings.USE_GPU else "3000k",
                    "b:a": "256k",
                    "avoid_negative_ts": "make_zero",
                    "preset": preset,
                },
            ).overwrite_output().run()
            temp_paths.append(temp_output)

        # Step 2: Create the concat list file
        with open(list_file, "w") as f:
            for temp_path in temp_paths:
                abs_path = os.path.abspath(temp_path)
                f.write(f"file '{abs_path}'\n")

        # Step 3: Concatenate the videos using demuxer, copying streams to avoid re-encoding
        ffmpeg.input(list_file, format="concat", safe=0).output(
            output_path,
            **{"c": "copy"},
        ).overwrite_output().run()

        logger.info(f"Videos concatenated at: {output_path}")

    except ffmpeg.Error as e:
        error_message = e.stderr.decode("utf8") if e.stderr else str(e)
        logger.error(f"FFmpeg error: {error_message}")

    finally:
        # Cleanup temporary files
        if os.path.exists(list_file):
            os.remove(list_file)
        for temp_path in temp_paths:
            if os.path.exists(temp_path):
                os.remove(temp_path)


def cut_video(
    input_path: str,
    output_path: str,
    start_time: float = None,
    end_time: float = None,
    duration: float = settings.MIN_VIDEO_DURATION,
    avoid_transitions: bool = True,
    preset: Literal["veryslow", "slow", "medium", "fast", "veryfast"] = settings.PRESET,
) -> None:
    """
    Cut a video between start_time and end_time and save it at output_path.

    Args:
        input_path (str): Path to the input video file.
        output_path (str): Path to the output video file.
        start_time (float): Start time in seconds.
        end_time (float): End time in seconds.
        duration (float): Duration of the output video in seconds. Default is MIN_VIDEO_DURATION.
        avoid_transitions (bool): Avoid transitions (intros/outros) between cuts. It will avoid
            the first and last 30 sec. of the video. Default is True.
        preset (literal["veryslow", "slow", "medium", "fast", "veryfast"]): Encoding preset.
            Default is "slow".
    """

    if os.path.exists(output_path):
        logger.info(f"Video already exists at: {output_path}")
        return

    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        input_duration = int(get_audio_duration(input_path))

        transition_length = 30
        if not start_time or not end_time:
            # Define valid range while avoiding the first and last 30 seconds
            min_start = (
                transition_length
                if avoid_transitions and input_duration > (transition_length * 2)
                else 0
            )
            max_end = (
                input_duration - transition_length
                if avoid_transitions and input_duration > (transition_length * 2)
                else input_duration
            )

            if max_end - min_start < duration:
                # If avoiding transitions makes the video too short, use the full range
                start_time = min_start
                end_time = max_end
                logger.info(
                    f"""Video too short to avoid transitions. Using full range:
                        - {start_time}s to {end_time}s.
                    """,
                )
            else:
                # Choose a random interval within the valid range
                start_time = random.randint(min_start, int(max_end - duration))
                end_time = start_time + int(duration)

        # Define output settings
        output_args = {
            "vcodec": "h264_videotoolbox" if settings.USE_GPU else "libx264",
            "acodec": "aac",
            "pix_fmt": "yuv420p",
            "t": end_time - start_time,
            "preset": preset,
            "crf": 18,
            "b:v": "5000k" if settings.USE_GPU else "3000k",
            "b:a": "256k",
        }

        (
            ffmpeg.input(input_path, ss=start_time)
            .output(output_path, **output_args)
            .overwrite_output()
            .run()
        )

        logger.info(
            f"Video cut between {start_time}s and {end_time}s at: {output_path}",
        )

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode('utf8')}")
        raise e


def resize_video(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
    zoom_crop: bool = False,
) -> None:
    """
    Resize a video to a specific width and height, optionally cropping to fill the frame.

    Args:
        input_path (str): Path to the input video file.
        output_path (str): Path to the output video file.
        width (int): Width of
        the output video.
        height (int): Height of the output video.
        zoom_crop (bool): Whether to crop the video to fill the entire screen (default: False).
    """

    if os.path.exists(output_path):
        logger.info(f"Video already exists at: {output_path}")
        return

    try:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if zoom_crop:
            # Scale up to cover the entire target resolution, then crop to the exact size
            filter_chain = (
                ffmpeg.input(input_path)
                .filter(
                    "scale",
                    f"iw*max({width}/iw,{height}/ih)",
                    f"ih*max({width}/iw,{height}/ih)",
                )
                .filter(
                    "crop",
                    width,
                    height,
                    "(iw - ow) / 2",
                    "(ih - oh) / 2",
                )  # Center crop
            )
        else:
            # Scale while maintaining aspect ratio, then pad to enforce exact resolution
            filter_chain = (
                ffmpeg.input(input_path)
                .filter(
                    "scale",
                    f"iw*min({width}/iw,{height}/ih)",
                    f"ih*min({width}/iw,{height}/ih)",
                )
                .filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")
            )

        (
            filter_chain.output(
                output_path,
                vcodec="h264_videotoolbox" if settings.USE_GPU else "libx264",
                acodec="aac",
                pix_fmt="yuv420p",
            )
            .overwrite_output()
            .run()
        )

        resize_info = "with cropping" if zoom_crop else "with padding"
        logger.info(
            f"Video resized {resize_info} to {width}x{height} at: {output_path}",
        )

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode('utf8')}")
        raise e


def combine_video_with_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    volume: float = 1.0,
) -> None:
    """
    Combine a video with an MP3 file, replacing the original audio.

    Args:
        video_path (str): Path to the input video file.
        audio_path (str): Path to the input MP3 file.
        output_path (str): Path to the output video file.
        volume (float): Volume level for the audio (default is 1.0).
    """
    try:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        video_duration = get_video_duration(video_path)
        audio_duration = get_audio_duration(audio_path)

        # Trim audio if it's longer than the video
        audio_input = ffmpeg.input(audio_path)
        if audio_duration > video_duration:
            audio_input = audio_input.filter("atrim", duration=video_duration)

        # Adjust volume
        audio_input = audio_input.filter("volume", volume)

        (
            ffmpeg.input(video_path)  # Input video
            .output(
                audio_input,
                output_path,
                vcodec="libx264",
                acodec="aac",
                pix_fmt="yuv420p",
                shortest=None,
            )
            .overwrite_output()
            .run()
        )

        logger.info(f"Video and audio combined successfully: {output_path}")

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode('utf8')}")
        raise e


def overlay_videos(
    background_video: str,
    overlay_video: str,
    output_path: str,
    preset: Literal["veryslow", "slow", "medium", "fast", "veryfast"] = settings.PRESET,
    position: str = "center",
    zoom: float = 1.0,
) -> None:
    """
    Overlay one video onto another while maintaining original audio levels and background
    resolution.

    The overlay video is scaled to fit inside the background (keeping its aspect ratio), with an
    optional zoom factor. The audio streams from both videos are processed (with aresample for the
    background and volume boost for the overlay) and then mixed.

    Args:
        background_video (str): The main background video
            (resolution & aspect ratio will be taken from here).
        overlay_video (str): The video that will be placed on top.
        output_path (str): Path to the output video file.
        preset (literal["veryslow", "slow", "medium", "fast", "veryfast"]): Encoding preset.
            Default is "slow".
        position (str): Position of the overlay video ('up', 'down', 'center', 'left', 'right').
            Default is 'center'.
        zoom (float): Scale factor for the overlay video
            (1.0 = default size, >1.0 = larger, <1.0 = smaller).
    """

    # check if output_path exists

    if os.path.exists(output_path):
        logger.info(
            f"Output file {output_path} already exists, skipping video overlay.",
        )
        return

    try:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Get background video resolution
        bg_probe = ffmpeg.probe(background_video)
        bg_width = int(bg_probe["streams"][0]["width"])
        bg_height = int(bg_probe["streams"][0]["height"])

        # Define positioning expressions
        positions = {
            "center": ("(main_w-overlay_w)/2", "(main_h-overlay_h)/2"),
            "up": ("(main_w-overlay_w)/2", "0"),
            "down": ("(main_w-overlay_w)/2", "main_h-overlay_h"),
            "left": ("0", "(main_h-overlay_h)/2"),
            "right": ("main_w-overlay_w", "(main_h-overlay_h)/2"),
        }
        x, y = positions.get(position, positions["center"])

        # Compute scaled size with zoom factor
        max_width = (
            bg_width / 2
        ) * zoom  # Default overlay width: half of background, adjusted by zoom
        max_height = (
            bg_height / 2
        ) * zoom  # Default overlay height: half of background, adjusted by zoom
        max_width = min(max_width, bg_width)
        max_height = min(max_height, bg_height)

        # Input streams
        bg = ffmpeg.input(background_video)
        ov = ffmpeg.input(overlay_video)

        # Scale overlay video while preserving aspect ratio
        # Get background frame rate from metadata
        bg_fps = bg_probe["streams"][0]["r_frame_rate"]

        ov_scaled = ov.video.filter("fps", fps=bg_fps).filter(
            "scale",
            f"min(iw,{max_width})",
            f"min(ih,{max_height})",
            force_original_aspect_ratio="decrease",
        )

        # Overlay the scaled video on top of the background video
        video_out = ffmpeg.overlay(bg.video, ov_scaled, x=x, y=y)
        bg_audio_fixed = bg.audio.filter("aresample", **{"async": 500}).filter(
            "volume",
            1.0,
        )
        ov_audio_fixed = ov.audio.filter("aresample", **{"async": 500}).filter(
            "volume",
            1.25,
        )

        # Mix the processed audio streams
        audio_out = ffmpeg.filter(
            [bg_audio_fixed, ov_audio_fixed],
            "amix",
            inputs=2,
            dropout_transition=0.2,
            duration="longest",
            normalize=False,
        )

        output_args = {
            "vcodec": "h264_videotoolbox" if settings.USE_GPU else "libx264",
            "acodec": "aac",
            "pix_fmt": "yuv420p",
            "preset": preset,
            "crf": 18,
            "b:v": "5000k" if settings.USE_GPU else "3000k",
            "b:a": "256k",
        }

        # Combine video and audio outputs and set output parameters.
        out = ffmpeg.output(video_out, audio_out, output_path, **output_args)
        out = out.overwrite_output()
        out.run()

        logger.info(
            f"Videos combined successfully with overlay at {position}, zoom={zoom}: {output_path}",
        )

    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode('utf8')}")
        raise e


def add_captions(
    input_file: str,
    output_file: str,
    subtitle_path: str,
) -> None:
    """
    Incorporate a ASS/SRT subtitle file into the input video.

    Args:
        input_file (str): The path of the input video.
        output_file (str): The path where the generated subtitle will be saved.
        subtitle_path (str): The path of the subtitle file.
    """

    try:
        video = ffmpeg.input(input_file)
        audio = video.audio
        ffmpeg.concat(video.filter("subtitles", subtitle_path), audio, v=1, a=1).output(
            output_file,
        ).run()
        logger.info(f"Subtitle added successfully to video at {output_file}")

    except Exception as e:
        logger.error(
            f"An error occurred while trying to embed subtitles in file {input_file}. Error: {e}",
        )
        raise e


def extract_video_thumbnail(video_path: str, output_path: str, time: int = 1):
    """
    Extracts a thumbnail from a video at a specified time using ffmpeg-python.

    Args:
        video_path (str): Path to the input video file.
        output_path (str): Path to save the extracted PNG thumbnail.
        time (int, optional): Time (in seconds) to extract the frame. Defaults to 1s.
    """

    # Check if thumbnail exists
    if os.path.exists(output_path):
        logger.info(f"Thumbnail already exists at {output_path}. Skipping extraction.")
        return

    try:
        (
            ffmpeg.input(video_path, ss=time)  # Seek to the given second
            .output(output_path, vframes=1)  # Extract 1 frame
            .run(
                overwrite_output=True,
                capture_stderr=True,
            )  # Capture errors for debugging
        )
        logger.info(f"Video thumbnail extracted successfully at {output_path}.")

    except ffmpeg.Error as e:
        logger.error(f"Error extracting video thumbnail: {e.stderr.decode()}")
        raise e
