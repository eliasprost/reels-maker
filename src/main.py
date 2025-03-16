# -*- coding: utf-8 -*-
import argparse
import asyncio
import json
import os
import random

import langid
import praw
from loguru import logger

from src.config import settings
from src.schemas import MediaFile, Speaker
from src.utils.media.audio import concatenate_audio_files, cut_audio
from src.utils.media.video import (
    add_captions,
    combine_video_with_audio,
    concatenate_videos,
    create_image_videoclip,
    cut_video,
    extract_video_thumbnail,
    get_video_duration,
    overlay_videos,
    resize_video,
)
from src.utils.reddit.post import parse_reddit_post
from src.utils.reddit.screenshot import take_comment_screenshot, take_post_screenshot
from src.utils.stt import stt
from src.utils.tts import tts


def main():

    # Get command line arguments. TODO: refactor this into a config file or something
    parser = argparse.ArgumentParser(description="Run the Reddit reels maker script")
    parser.add_argument("--url", type=str, default="", help="URL Reddit post")
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of comments to process",
    )
    args = parser.parse_args()

    URL = args.url
    while not URL.startswith("https://www.reddit.com"):
        URL = input("Invalid URL format. Please enter a valid Reddit post URL: ")

    # MAIN ARGS
    N_COMMENTS = (
        args.n
    )  # TODO: we need to change to use the video duration from settings.
    REDDIT_VIDEO_PATH = "assets/posts/{post_id}/video/reddit_video.mp4"
    BACKGROUND_VIDEO_PATH = "assets/posts/{post_id}/video/background_video_{suffix}.mp4"
    BACKGROUND_AUDIO_PATH = "assets/posts/{post_id}/audio/background_audio.mp3"
    BACKGROUND_AUDIO_VOLUME = (
        0.15  # TODO: we need to change this to use the video duration from settings.
    )
    REEL_PATH = "assets/posts/{post_id}/reel_{suffix}.mp4"
    SPEAKER = "Abrahan Mack"
    AUDIO_SPEED = (
        1.3  # TODO: we need to change this to use the video duration from settings.
    )
    THEME = "light"

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

    # Create asset post folder if it doesn't exist
    if not os.path.exists(f"./assets/posts/{post.post_id}"):
        os.makedirs(f"./assets/posts/{post.post_id}", exist_ok=True)

    # Set logs
    logger.add(f"./assets/posts/{post.post_id}/logs.log")

    # Detect post language using post body
    supported_langs = [
        lang["lang_code"] for lang in json.load(open("./data/languages.json"))
    ]
    language = langid.classify(post.title + ": " + post.body)[0].strip()
    logger.info(f"Post {post.post_id} detected as {language}")

    if language not in supported_langs:
        error = f"{language} not supported. Please, choose a supported language: {supported_langs}"
        logger.error(error)
        raise ValueError(error)

    # Generate post audio files and
    speaker = Speaker(name=SPEAKER)

    tts.generate_audio_clip(
        post.title,
        language=language,
        output_path=post.title_audio_path,
        speaker=speaker.name,
        speed=AUDIO_SPEED,
    )
    tts.generate_audio_clip(
        post.body,
        language=language,
        speaker=speaker.name,
        output_path=post.body_audio_path,
        speed=AUDIO_SPEED,
    )

    # We filter None values to deal with post without body text
    post_audios = list(filter(None, [post.title_audio_path, post.body_audio_path]))

    concatenate_audio_files(
        files=post_audios,
        # TODO: we need to change this to use the video duration from settings.
        silence_duration=0.2,
        output_file=post.audio_path,
    )

    # Get the post screenshot
    asyncio.run(take_post_screenshot(post, THEME))

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
        tts.generate_audio_clip(
            comment.body,
            speaker=speaker.name,
            language=language,
            output_path=comment.audio_path,
            speed=AUDIO_SPEED,
        )

    # Get the comments screenshots
    for comment in top_comments:
        asyncio.run(take_comment_screenshot(comment, THEME))

    # Generate comments videos: combine audio and image
    for comment in top_comments:
        create_image_videoclip(
            image_path=comment.image_path,
            audio_path=comment.audio_path,
            output_path=comment.video_path,
        )

    # Generate outro clip
    outro = [
        lang["outro"]
        for lang in json.load(open("./data/languages.json"))
        if lang["lang_code"] == language
    ]

    if len(outro) == 0:
        logger.error(f"Language {language} outro not found.")
        raise ValueError(f"Language {language} outro not found.")
    else:
        tts.generate_audio_clip(
            text=outro[0],
            language=language,
            output_path=f"./assets/others/outros/outro_{language}_{speaker.id}.mp3",
            speaker=speaker.name,
            speed=AUDIO_SPEED,
        )

    create_image_videoclip(
        image_path="./assets/others/outros/outro.png",
        audio_path=f"./assets/others/outros/outro_{language}_{speaker.id}.mp3",
        output_path=f"./assets/others/outros/outro_{language}_{speaker.id}.mp4",
    )

    # MAIN VIDEO
    # Reddit video
    # Concatenate all videos
    all_videos = (
        [post.video_path]
        + [comment.video_path for comment in top_comments]
        + [f"./assets/others/outros/outro_{language}_{speaker.id}.mp4"]
    )
    concatenate_videos(all_videos, REDDIT_VIDEO_PATH.format(post_id=post.post_id))

    # Background video
    # Get reddit reference video duration
    video_duration = get_video_duration(REDDIT_VIDEO_PATH.format(post_id=post.post_id))

    # Get and download a random background videos and audio
    audios = [
        MediaFile(**audio) for audio in json.load(open("./data/background_audios.json"))
    ]

    videos = [
        MediaFile(**video) for video in json.load(open("./data/background_videos.json"))
    ]

    # Get a random background video and audio
    random_video = random.choice(videos)
    random_audio = random.choice(audios)

    # Download random audio and video
    random_audio.download()
    random_video.download()

    # Cut and resize the background video
    cut_video(
        input_path=random_video.path,
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
        input_path=random_audio.path,
        output_path=BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
        duration=video_duration,
        fade_duration=1,  # TODO: we need to change this to use the video duration from settings.
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
        zoom=1.85,  # TODO: we need to change this to use the video duration from settings.
    )

    # Add subtitles to the video
    subs_segments = stt.transcribe_audio(
        input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        language=language,
    )

    # Generate SRT file
    stt.generate_srt_file(
        segments=subs_segments,
        input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        output_directory=f"assets/posts/{post.post_id}/",
    )

    # Transform SRT to ASS format
    stt.srt_to_ass(
        input_file=f"assets/posts/{post.post_id}/reel_raw.srt",
        delete_srt=True,
    )

    # Add subtitle to video
    add_captions(
        input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        output_file=REEL_PATH.format(post_id=post.post_id, suffix="subtitled"),
        subtitle_path=f"assets/posts/{post.post_id}/reel_raw.ass",
    )

    # Extract video thumbnail from the subtitled video
    extract_video_thumbnail(
        video_path=REEL_PATH.format(post_id=post.post_id, suffix="subtitled"),
        output_path=f"assets/posts/{post.post_id}/thumbnail.png",
    )


if __name__ == "__main__":
    main()
