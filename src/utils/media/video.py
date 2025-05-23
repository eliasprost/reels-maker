# -*- coding: utf-8 -*-
import os
import random
import tempfile
from pathlib import Path
from typing import List, Literal

import ffmpeg
import pysubs2
from loguru import logger
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

from src.config import settings
from src.utils.common import create_file_folder
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
        # Create the parent folder of the output path if it doesn't exist
        create_file_folder(output_path)

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
            ffmpeg.output(
                input_image,
                input_audio,
                output_path,
                loglevel="quiet",
                **output_args,
            )
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
            temp_output = str(Path(settings.TEMP_PATH) / f"temp_normalized_{idx}.mp4")
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
    transition_duration: int = 30,
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
        transition_duration (int): Remove seconds from the start and end of the video to avoid
            transitions (intros/outros) between cuts. The default value is 30 seconds.
        preset (literal["veryslow", "slow", "medium", "fast", "veryfast"]): Encoding preset.
            Default is "slow".
    """

    if os.path.exists(output_path):
        logger.info(f"Video already exists at: {output_path}")
        return

    try:
        # Create output directory if it doesn't exist
        create_file_folder(output_path)

        input_duration = int(get_audio_duration(input_path))

        if not start_time or not end_time:
            # Define valid range while avoiding the first and last 30 seconds
            min_start = (
                transition_duration
                if transition_duration > 0
                and input_duration > (transition_duration * 2)
                else 0
            )
            max_end = (
                input_duration - transition_duration
                if transition_duration > 0
                and input_duration > (transition_duration * 2)
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
        # Create output directory if it doesn't exist
        create_file_folder(output_path)

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

    # check if video exist
    if os.path.exists(output_path):
        logger.info(f"Video already exists: {output_path}")
        return

    try:
        # Create the output directory if it doesn't exist
        create_file_folder(output_path)

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
    overlay_videos: List[str],
    output_path: str,
    position: Literal["center", "left", "right", "top", "bottom"] = "center",
    zoom: float = 1.0,
    preset: Literal["veryslow", "slow", "medium", "fast", "veryfast"] = settings.PRESET,
    margin: int = 50,  # Margin in pixels on each side
    normalize_audio: bool = True,  # Enable audio normalization
) -> None:
    """
    Overlays multiple videos onto a background video without concatenating them,
    by placing each overlay video sequentially in time and positioning them within
    an area that respects a specified margin from the background video's edges.

    Args:
        background_video (str): Path to the background video file.
        overlay_videos (List[str]): List of paths to overlay video files.
            You can pas a 'GAP:<duration>' placeholder to create a space of the specified duration.
                Example: ['video_1.mp4', 'GAP:5.23', 'video_2.mp4'].
            Also, you can pass audio files (mp3, wav) to add a gap with the audio duration. The
            audio will be added to the background video.
                Example: ['video_1.mp4', 'audio_1.mp3', 'video_2.mp4'].
        output_path (str): Path to save the output video file.
        position (str, optional): Desired alignment for the overlay videos within the available
            area. Accepted: "center", "left", "right", "top", and "bottom". Default is "center".
        zoom (float, optional): A zoom factor for resizing the overlay videos. A value of 1.0 means
            the overlay is scaled to the maximum size that fits within the available area.
        preset (str, optional): The encoding preset for the output video.
            Default is taken from settings.PRESET.
        margin (int, optional): Margin in pixels between the overlay videos and the
            background edges. Default is 50 pixels on each side.
        normalize_audio (bool, optional): Whether to normalize the audio of overlay videos.
    """

    # Check if the video already exists
    if os.path.exists(output_path):
        logger.info(f"Video already exists at: {output_path}")
        return

    # Create the parent folder of the output path if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # First pass: calculate total overlay duration
    total_overlay_duration = 0
    overlay_durations = []

    for video_path in overlay_videos:
        # Check if the video path is a gap (e.g., "GAP:5")
        if video_path.startswith("GAP:"):
            try:
                gap_duration = float(video_path.split(":")[1])
                overlay_durations.append(gap_duration)
                total_overlay_duration += gap_duration
                continue
            except Exception as e:
                logger.error(f"Invalid gap format: {video_path} ({e})")
                continue

        # Check if is an audio file
        if video_path.endswith(".mp3") or video_path.endswith(".wav"):
            gap_duration = get_audio_duration(video_path)
            overlay_durations.append(gap_duration)
            total_overlay_duration += gap_duration
            continue

        try:
            clip = VideoFileClip(video_path)
            overlay_durations.append(clip.duration)
            total_overlay_duration += clip.duration
            clip.close()
        except Exception as e:
            logger.error(f"Error calculating duration for {video_path}: {e}")
            overlay_durations.append(0)

    if total_overlay_duration <= 0:
        raise ValueError("No valid overlay videos provided or total duration is zero.")

    # Load background video and ensure it's long enough
    bg_clip = VideoFileClip(background_video)
    bg_duration = bg_clip.duration

    if bg_duration < total_overlay_duration:
        logger.warning(
            f"""
            Background video ({bg_duration}s) is shorter than total overlay
            duration ({total_overlay_duration}s). Looping background.
            """,
        )

        # Calculate how many loops we need
        loops_needed = int(total_overlay_duration // bg_duration) + 1
        bg_clips = [bg_clip] * loops_needed
        bg_clip = concatenate_videoclips(bg_clips)

        # Trim to exact needed duration
        bg_clip = bg_clip.subclip(0, total_overlay_duration)

    bg_fps = bg_clip.fps if bg_clip.fps else 30
    bg_width, bg_height = bg_clip.size

    # Define the available area (background minus margins)
    available_width = bg_width - 2 * margin
    available_height = bg_height - 2 * margin

    # Map the provided position to a standardized alignment value
    pos_map = {
        "up": "top",
        "down": "bottom",
        "center": "center",
        "left": "left",
        "right": "right",
    }
    mapped_position = pos_map.get(position.lower(), "center")

    # Helper function to compute the (x, y) position within the available area
    def _compute_position(
        alignment: str,
        new_width: int,
        new_height: int,
    ) -> tuple[int, int]:
        if alignment == "center":
            x = margin + (available_width - new_width) // 2
            y = margin + (available_height - new_height) // 2
        elif alignment == "left":
            x = margin
            y = margin + (available_height - new_height) // 2
        elif alignment == "right":
            x = bg_width - margin - new_width
            y = margin + (available_height - new_height) // 2
        elif alignment == "top":
            x = margin + (available_width - new_width) // 2
            y = margin
        elif alignment == "bottom":
            x = margin + (available_width - new_width) // 2
            y = bg_height - margin - new_height
        else:
            x = margin + (available_width - new_width) // 2
            y = margin + (available_height - new_height) // 2
        return (x, y)

    # Process each overlay video
    overlay_clips = []
    current_time = 0  # Start time offset for sequential playback

    for i, video_path in enumerate(overlay_videos):

        # Skip if the video path is a placeholder for a gap
        if video_path.startswith("GAP:"):
            current_time += overlay_durations[i]
            continue

        # Add a transparent placeholder video if is an audio file
        # Check if is an audio file
        if video_path.endswith(".mp3") or video_path.endswith(".wav"):
            audio_clip = AudioFileClip(video_path)
            duration = audio_clip.duration
            placeholder_clip = (
                ColorClip(size=(10, 10), color=(0, 0, 0), duration=duration)
                .set_opacity(0)
                .set_audio(audio_clip)
                .set_start(current_time)
            )
            overlay_clips.append(placeholder_clip)
            current_time += duration
            continue

        try:
            clip = VideoFileClip(video_path)
            clip_fps = clip.fps if clip.fps else bg_fps
            clip_width, clip_height = clip.size

            # Compute scale factor so the clip fits within the available area (then apply zoom)
            scale_factor = (
                min(available_width / clip_width, available_height / clip_height) * zoom
            )
            new_width = int(clip_width * scale_factor)
            new_height = int(clip_height * scale_factor)

            # Compute the (x, y) position within the available area
            pos = _compute_position(mapped_position, new_width, new_height)

            # Resize video
            resized_clip = clip.resize((new_width, new_height)).set_fps(clip_fps)

            # Normalize audio volume (optional)
            if normalize_audio and resized_clip.audio:
                resized_clip = resized_clip.volumex(
                    1.2,
                )  # Adjust to balance audio levels

            # Set the start time for sequential playback
            resized_clip = resized_clip.set_start(current_time).set_position(pos)
            current_time += overlay_durations[i]  # Use pre-calculated duration

            overlay_clips.append(resized_clip)

        except Exception as e:
            logger.error(f"Error processing {video_path}: {e}")
            continue

    if not overlay_clips:
        raise ValueError("No valid overlay videos could be processed.")

    # Trim the background video to exactly match the total overlay duration
    bg_clip = bg_clip.subclip(0, total_overlay_duration)

    # Composite the background with the overlay clips
    composite = CompositeVideoClip([bg_clip] + overlay_clips, size=bg_clip.size)
    composite.duration = total_overlay_duration  # Ensure correct duration

    # Write the final video
    composite.write_videofile(
        output_path,
        fps=bg_fps,
        codec="h264_videotoolbox" if settings.USE_GPU else "libx264",
        audio_codec="aac",
        preset=preset,
        threads=4,  # Add threads parameter for better performance
        ffmpeg_params=["-movflags", "+faststart"],  # For better streaming
    )

    # Cleanup resources
    bg_clip.close()
    for clip in overlay_clips:
        clip.close()

    logger.info(f"Video with overlays created successfully: {output_path}")


def add_captions(
    input_file: str,
    output_file: str,
    caption_path: str,
    font_path: str = "assets/fonts",
) -> None:
    """
    Incorporate a ASS/SRT subtitle file into the input video.

    Args:
        input_file (str): The path of the input video.
        output_file (str): The path where the generated subtitle will be saved.
        caption_path (str): The path of the subtitle file.
        font_path (str, optional): The path of the font file. Defaults to assets/fonts.
            This path file must be defined correctly inif the subtitle file uses a custom font.
    """

    # check if output_path exists
    if os.path.exists(output_file):
        logger.info(
            f"Output file {output_file} already exists, skipping video overlay.",
        )
        return

    try:
        # Create output directory if it doesn't exist
        create_file_folder(output_file)
        video = ffmpeg.input(input_file)
        audio = video.audio

        video = video.filter(
            "subtitles",
            caption_path,
            fontsdir=(
                Path(font_path).parent if font_path.endswith(".ttf") else font_path
            ),
        )
        ffmpeg.concat(video, audio, v=1, a=1).output(
            output_file,
            loglevel="quiet",
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
        # Create output directory if it doesn't exist
        create_file_folder(output_path)
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


def add_fade_out(input_path: str, fade_duration: float = 1.5, output_path: str = None):
    """
    Adds a fade-to-black effect at the end of a video using moviepy.

    Args:
        input_path (str): Path to input video.
        fade_duration (float): Duration (in seconds) of the fade effect. Default is 1.5.
        output_path (str): Path to save the output video. Default is None.
            If None, it will overwrite the input video.
    """
    clip = VideoFileClip(input_path)
    faded = clip.fx(vfx.fadeout, duration=fade_duration)

    # Determine where to write
    if output_path:
        target = output_path
    else:
        # temp file in same directory
        base, ext = os.path.splitext(input_path)
        tmp = tempfile.NamedTemporaryFile(
            dir=settings.TEMP_PATH,
            prefix=os.path.basename(base) + "_fade_",
            suffix=ext,
            delete=False,
        )
        tmp.close()
        target = tmp.name

    # Write out
    faded.write_videofile(target, codec="libx264", audio_codec="aac")

    # If no explicit output, replace original
    if output_path is None:
        os.replace(target, input_path)

    clip.close()
    faded.close()


def shift_caption_start(
    input_file: str,
    start_time: float,
    output_file: str = None,
) -> None:
    """
    Moves the first dialogue to a new start time, mantaining the rest of the dialogues in
    the same order and duration.

    Args:
        input_file (str): Path to the input ASS file.
        start_time (float): Time in seconds to set as start time of the first line.
        output_file (str): Path to the output ASS file. Default is None.
            If None, the input file will be overwritten.
    """

    subs = pysubs2.load(input_file)

    # Standarize start dialogue to be at 0.0 ms
    subs.shift(ms=-subs[0].start)

    # # Shift to start with the new start time
    subs.shift(ms=start_time * 1000)

    # Save
    subs.save(output_file if output_file else input_file)
