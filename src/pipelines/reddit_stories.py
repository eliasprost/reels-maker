# -*- coding: utf-8 -*-

import re
from typing import List, Optional, Union

from loguru import logger

from src.pipelines.schemas import RedditVideoPipeline
from src.schemas import CaptionStyle, RedditPost, Speaker
from src.utils.media.video import (
    add_captions,
    add_fade_out,
    create_image_videoclip,
    extract_video_thumbnail,
    get_video_duration,
    overlay_videos,
    shift_caption_start,
)
from src.utils.reddit.post import get_reddit_object
from src.utils.reddit.screenshot import take_post_screenshot


class RedditStoriesPipeline(RedditVideoPipeline):
    """
    A class for creating videos from Reddit post stories.
    """

    def __init__(
        self,
        name: str = "reddit_stories_video_pipeline",
        description: str = "A pipeline for creating videos from Reddit post stories",
        speaker: Optional[Union[str, Speaker]] = None,
        captions: Optional[CaptionStyle] = None,
        audio_speed: float = 1.3,
        background_audio_volume: float = 0.15,
        background_video_name: Optional[str] = None,
        background_audio_name: Optional[str] = None,
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            captions=captions,
            background_video_name=background_video_name,
            background_audio_name=background_audio_name,
            background_audio_volume=background_audio_volume,
        )

        self.audio_speed = audio_speed
        self.speaker = speaker

        # Paths and config
        self.reel_path = "assets/posts/{post_id}/reel_{suffix}.mp4"
        self.background_video_path = (
            "assets/posts/{post_id}/video/background_video_{suffix}.mp4"
        )
        self.background_audio_path = "assets/posts/{post_id}/audio/background_audio.mp3"

    def generate_title_media(self, post: RedditPost) -> None:
        """
        Generate audio, get the already generated image and creathe the video clips from the Reddit
        post title.

        Args:
            post (RedditPost): The Reddit post object.
        """
        # Audio
        self.tts.generate_audio_clip(
            post.title,
            output_path=post.title_audio_path,
            speaker=self.speaker,
            speed=self.audio_speed,
        )

        # Video
        create_image_videoclip(
            image_path=post.image_path,
            audio_path=post.title_audio_path,
            output_path=post.video_path,
        )

    def generate_reel_video(
        self,
        post: RedditPost,
        background_video: str,
        overlay_media: List[str],
        captions: CaptionStyle = None,
        video_text: str = None,
    ) -> None:
        """
        Combine Reddit and Background videos into a single reel video.

        Args:
            post (RedditPost): Reddit post object.
            background_video (str): Path to the background video.
            overlay_media (List[str]): List of paths to the overlay videos.
            captions (CaptionStyle): Caption style object. Defaults to None.
                If no captions is provided, no captions will be added.
        """

        # Combine Reddit and Background videos
        overlay_videos(
            background_video=background_video,
            overlay_videos=overlay_media,
            output_path=self.reel_path.format(post_id=post.post_id, suffix="raw"),
        )

        if captions and video_text:
            # Generate captions
            self.stt.generate_captions(
                input_file=post.body_audio_path,
                text=video_text,
                language=post.language,
                output_file=f"assets/posts/{post.post_id}/reel_raw.ass",
                style=self.captions,
            )

            # Modify captions to start after the title video
            title_duration = get_video_duration(overlay_media[0])

            shift_caption_start(
                input_file=f"assets/posts/{post.post_id}/reel_raw.ass",
                start_time=title_duration,
            )

            # Add subtitle to video
            add_captions(
                input_file=self.reel_path.format(post_id=post.post_id, suffix="raw"),
                output_file=self.reel_path.format(
                    post_id=post.post_id,
                    suffix="subtitled",
                ),
                caption_path=f"assets/posts/{post.post_id}/reel_raw.ass",
                font_path=self.captions.font_path,
            )

        # Add final fade out
        add_fade_out(
            input_path=self.reel_path.format(
                post_id=post.post_id,
                suffix="subtitled" if captions else "raw",
            ),
        )

        # Extract thumbnail
        extract_video_thumbnail(
            video_path=self.reel_path.format(
                post_id=post.post_id,
                suffix="subtitled" if captions else "raw",
            ),
            output_path=f"assets/posts/{post.post_id}/thumbnail.png",
        )

        logger.info(f"Video created for post {post.post_id}")

    async def run(self, url: str) -> None:
        """
        Run the Reddit Comments Pipeline to generate a rell video from Reddit comments.

        Args:
            url (str): The URL of the Reddit post.
        """

        logger.info("Starting Reddit Stories Pipeline...")

        # Get post object
        post = get_reddit_object(url)
        logger.info(f"Post retrieved: {post.title}")

        # Build Speaker if it was not forced
        if not isinstance(self.speaker, Speaker):
            self.speaker = Speaker(name=self.speaker, language=post.language)

        else:
            if self.speaker.language != post.language:
                logger.warning(
                    f"Speaker language ({self.speaker.language}) does not match post language ({post.language}).",  # noqa: E501
                )

        # Take post title screenshot
        await take_post_screenshot(post, elements=["header", "title", "action_row"])

        # Generate media for post
        self.generate_title_media(post)
        logger.info(f"Media generated for the post title: {post.title}")

        # Generate story audio
        self.tts.generate_audio_clip(
            post.body,
            output_path=post.body_audio_path,
            speaker=self.speaker,
            speed=self.audio_speed,
        )
        logger.info(f"Audio generated for the post body: {post.body}")

        # Combine media
        overlay_media = [post.video_path, post.body_audio_path]

        overlay_duration = sum(get_video_duration(video) for video in overlay_media) + 1

        # Generate media for background video
        background_video = self.get_background_video(
            post=post,
            duration=overlay_duration,
            video_file=self.background_video_name,
            audio_file=self.background_audio_name,
            video_condition={"topic": "satisfying"},
        )

        logger.info(f"Background video generated at: {background_video}")

        # Clean and save subtitles text
        cleaned_text = re.sub(r"[()]", ",", post.body)
        with open(f"assets/posts/{post.post_id}/video_text.txt", "w") as f:
            f.write(cleaned_text)

        # Combine all videos
        self.generate_reel_video(
            post=post,
            background_video=background_video,
            overlay_media=overlay_media,
            captions=self.captions,
            video_text=cleaned_text if self.captions else None,
        )

        self.save_record(post)


reddit_stories_pipeline = RedditStoriesPipeline(
    captions=CaptionStyle(
        fontname="Fira Sans",
        fontsize=22,
        alignment="middle",
        marginv=60,
        primarycolor=(255, 255, 255, 1),
        secondarycolor=(255, 255, 255, 1),
        outlinecolor=(30, 30, 30, 1),
        bold=True,
        word_levels=True,
        segment_level=False,
        outline=2,
    ),
)
