# -*- coding: utf-8 -*-
import asyncio
import json
import random

import praw

from src.config import settings
from src.utils.background import download_file, parse_file
from src.utils.media.audio import concatenate_audio_files, cut_audio, get_audio_duration
from src.utils.media.video import (
    add_subtitle_to_video,
    combine_video_with_audio,
    concatenate_videos,
    create_image_videoclip,
    cut_video,
    overlay_videos,
    resize_video,
)
from src.utils.reddit.post import parse_reddit_post
from src.utils.reddit.screenshot import take_comment_screenshot, take_post_screenshot
from src.utils.stt import speech_to_text
from src.utils.tts import text_to_speech


def main():

    # Add a sys arg to take the URL from the CLI
    URL = input("Enter the URL of the Reddit post: ")

    if not URL.startswith("https://www.reddit.com"):
        raise ValueError("Invalid URL format. Please enter a valid Reddit post URL.")

    # MAIN ARGS
    N_COMMENTS = 3  # TODO: we need to change for video duration.
    REDDIT_VIDEO_PATH = "assets/posts/{post_id}/video/reddit_video.mp4"
    REDDIT_AUDIO_PATH = "assets/posts/{post_id}/audio/reddit_audio.mp3"
    BACKGROUND_VIDEO_PATH = "assets/posts/{post_id}/video/background_video_{suffix}.mp4"
    BACKGROUND_AUDIO_PATH = "assets/posts/{post_id}/audio/background_audio.mp3"
    BACKGROUND_AUDIO_VOLUME = 0.30
    REEL_PATH = "assets/posts/{post_id}/reel_{suffix}.mp4"

    # POST
    # Get Reddit post
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent="Accessing Reddit threads",
        username=settings.REDDIT_USER_NAME,
        passkey=settings.REDDIT_USER_PASSWORD,
        check_for_async=False,
    )

    post = parse_reddit_post(reddit.submission(url=URL))

    # Generate post audio files and
    text_to_speech.generate_audio_clip(
        post.title,
        output_path=post.title_audio_path,
        speed=1.3,
    )
    text_to_speech.generate_audio_clip(
        post.body,
        output_path=post.body_audio_path,
        speed=1.3,
    )

    concatenate_audio_files(
        files=[post.title_audio_path, post.body_audio_path],
        silence_duration=0.2,
        output_file=post.audio_path,
    )

    # Get the post screenshot
    asyncio.run(take_post_screenshot(post))

    # Generate post video: combine audio and image
    create_image_videoclip(
        image_path=post.image_path,
        audio_path=post.audio_path,
        output_path=post.video_path,
    )

    # COMMENTS
    # Get comments info
    top_comments = sorted(post.comments, key=lambda x: x.score, reverse=True)[
        :N_COMMENTS
    ]
    # TODO: we need to define a strategy to get the best comments.

    # Generate audio files for comments
    for comment in top_comments:
        text_to_speech.generate_audio_clip(
            comment.body,
            output_path=comment.audio_path,
            speed=1.3,
        )

    # Get the comments screenshots
    for comment in top_comments:
        asyncio.run(take_comment_screenshot(comment))

    # Generate comments videos: combine audio and image
    for comment in top_comments:
        create_image_videoclip(
            image_path=comment.image_path,
            audio_path=comment.audio_path,
            output_path=comment.video_path,
        )

    # MAIN VIDEO
    # Reddit video
    # Concatenate all videos
    all_videos = [post.video_path] + [comment.video_path for comment in top_comments]
    concatenate_videos(all_videos, REDDIT_VIDEO_PATH.format(post_id=post.post_id))

    # Concatenate all audios
    all_audios = [post.audio_path] + [comment.audio_path for comment in top_comments]
    concatenate_audio_files(
        files=all_audios,
        silence_duration=0.1,
        output_file=REDDIT_AUDIO_PATH.format(post_id=post.post_id),
    )

    # Background video
    # Get reddit reference video duration
    # TEMP
    video_duration = get_audio_duration(REDDIT_VIDEO_PATH.format(post_id=post.post_id))

    # Get and download a random background videos and audio
    audios = [
        parse_file(audio) for audio in json.load(open("./data/background_audios.json"))
    ]

    videos = [
        parse_file(video) for video in json.load(open("./data/background_videos.json"))
    ]

    # Get a random background video and audio
    random_video = random.choice(videos)
    random_audio = random.choice(audios)

    # Download random audio and video
    download_file(random_audio)
    download_file(random_video)

    random_video_path = f"assets/background/video/{random_video.file_name}"
    random_audio_path = f"assets/background/audio/{random_audio.file_name}"

    # Cut and resize the background video
    cut_video(
        input_path=random_video_path,
        output_path=BACKGROUND_VIDEO_PATH.format(post_id=post.post_id, suffix="cutted"),
        duration=video_duration,
    )

    resize_video(
        input_path=BACKGROUND_VIDEO_PATH.format(post_id=post.post_id, suffix="cutted"),
        output_path=BACKGROUND_VIDEO_PATH.format(
            post_id=post.post_id,
            suffix="cutted_croped",
        ),
        height=settings.SCREEN_HEIGHT,
        width=settings.SCREEN_WIDTH,
        zoom_crop=True,
    )

    # Cut the background audio
    cut_audio(
        input_path=random_audio_path,
        output_path=BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
        duration=video_duration,
        fade_duration=1,
    )

    # Combine background video and audio
    combine_video_with_audio(
        video_path=BACKGROUND_VIDEO_PATH.format(
            post_id=post.post_id,
            suffix="cutted_croped",
        ),
        audio_path=BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
        output_path=BACKGROUND_VIDEO_PATH.format(
            post_id=post.post_id,
            suffix="finished",
        ),
        volume=BACKGROUND_AUDIO_VOLUME,
    )

    # Combine Reddit and Background videos
    overlay_videos(
        background_video=BACKGROUND_VIDEO_PATH.format(
            post_id=post.post_id,
            suffix="finished",
        ),
        overlay_video=REDDIT_VIDEO_PATH.format(post_id=post.post_id),
        output_path=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        zoom=1.85,
    )

    # Add subtitles to the video
    subs_segments = speech_to_text.transcribe_audio(
        input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        language="es",
    )

    # Generate SRT file
    speech_to_text.generate_srt_file(
        segments=subs_segments,
        input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        output_directory=f"assets/posts/{post.post_id}/",
    )

    # Transform SRT to ASS format
    speech_to_text.srt_to_ass(
        input_file=f"assets/posts/{post.post_id}/reel_raw.srt",
        delete_srt=True,
    )

    # Add subtitle to video
    add_subtitle_to_video(
        input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        output_file=REEL_PATH.format(post_id=post.post_id, suffix="subtitled"),
        subtitle_path=f"assets/posts/{post.post_id}/reel_raw.ass",
    )


if __name__ == "__main__":
    main()
