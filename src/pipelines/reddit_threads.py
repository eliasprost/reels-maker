# -*- coding: utf-8 -*-

import asyncio
from typing import List, Literal, Optional, Tuple

from loguru import logger
from tqdm import tqdm

from src.config import settings
from src.pipelines.schemas import RedditVideoPipeline
from src.schemas import CaptionStyle, RedditComment, RedditPost, Speaker
from src.utils.media.audio import concatenate_audio_files, get_audio_duration
from src.utils.media.video import (
    add_captions,
    create_image_videoclip,
    extract_video_thumbnail,
    get_video_duration,
    overlay_videos,
)
from src.utils.reddit.post import get_reddit_object
from src.utils.reddit.screenshot import take_comment_screenshot, take_post_screenshot


class RedditThreadPipeline(RedditVideoPipeline):
    """
    A class for creating videos from Reddit post comments.
    """

    def __init__(
        self,
        name: str = "reddit_comments_video_pipeline",
        description: str = "A pipeline for creating videos from Reddit and their comments",
        speaker: Optional[str] = None,
        captions: Optional[CaptionStyle] = None,
        theme: Literal["dark", "light"] = "light",
        audio_speed: float = 1.3,
        background_audio_volume: float = 0.20,
        background_video_name: Optional[str] = None,
        background_audio_name: Optional[str] = None,
        max_comment_length: int = 150,
        silence_duration: float = 0.2,
        remove_duplicates: bool = True,
        sort_by_score: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            speaker=speaker,
            captions=captions,
            background_video_name=background_video_name,
            background_audio_name=background_audio_name,
            background_audio_volume=background_audio_volume,
        )

        self.remove_duplicates = remove_duplicates
        self.sort_by_score = sort_by_score
        self.theme = theme
        self.audio_speed = audio_speed
        self.speaker = Speaker(name=speaker)
        self.max_comment_length = max_comment_length
        self.silence_duration = silence_duration

        # Paths and config
        self.reel_path = "assets/posts/{post_id}/reel_{suffix}.mp4"
        self.background_video_path = (
            "assets/posts/{post_id}/video/background_video_{suffix}.mp4"
        )
        self.background_audio_path = "assets/posts/{post_id}/audio/background_audio.mp3"

    def get_comments(
        self,
        post: RedditPost,
        sort_by_score: bool = False,
        filter_duplicates: bool = True,
    ) -> List[RedditComment]:
        """
        Get comments from the Reddit post. We are filtering out comments that are too long.
        Also we are sorting the comments by score descending.

        Args:
            post (RedditPost): The Reddit post object.
            sort_by_score (bool): Whether to sort the comments by score.
            filter_duplicates (bool): Whether to filter out duplicate comments.
        """

        comments = [
            comment
            for comment in post.comments
            if comment.length <= self.max_comment_length
        ]

        if sort_by_score:
            comments = sorted(comments, key=lambda x: x.score, reverse=True)

        if filter_duplicates:
            comments = self.filter_duplicate_comments(comments)

        duration = 0
        processed_comments = []
        for comment in comments:
            # Audio
            self.tts.generate_audio_clip(
                comment.body,
                speaker=self.speaker.name,
                language=post.language,
                output_path=comment.audio_path,
                speed=self.audio_speed,
            )

            duration += get_audio_duration(comment.audio_path)
            processed_comments.append(comment)

            if duration < settings.MIN_VIDEO_DURATION:
                duration += self.silence_duration
                continue

            else:
                break

        return processed_comments

    def filter_duplicate_comments(
        self,
        comments: List[RedditComment],
        threshold: float = 0.80,
        alpha: float = 0.5,
    ) -> List[RedditComment]:
        """
        Filter out duplicate comments using hybrid semantic + lexical similarity.

        Args:
            comments: List of RedditComment objects to filter.
            threshold: Minimum similarity score to consider as duplicate (0-1).
            alpha: Weight for hybrid search (0=BM25, 1=vector).
        """
        if not comments:
            return []

        comment_bodies = [c.body for c in comments]
        self.vector_store.add_documents(comment_bodies)
        unique_comments, seen = [], set()

        for i, body in enumerate(comment_bodies):
            if i in seen:
                continue

            unique_comments.append(comments[i])
            seen.add(i)

            for sim_body, score in self.vector_store.hybrid_search(
                body,
                k=len(comment_bodies),
                alpha=alpha,
            ):
                if sim_body != body and score >= threshold:
                    seen.add(comment_bodies.index(sim_body))

        logger.info(
            f"Filtered {len(comments) - len(unique_comments)} duplicate comments",
        )
        return unique_comments

    async def take_screenshots(
        self,
        post: RedditPost,
        comments: List[RedditComment],
    ) -> None:
        """
        Take the post and comments screenshots using the async api of playwright.
        Args:
            post (RedditPost): The Reddit post object.
            comments (List[RedditComment]): The list of comments to take screenshots from.
        """
        await asyncio.gather(
            take_post_screenshot(post, theme=self.theme),
            *(
                take_comment_screenshot(comment, theme=self.theme)
                for comment in comments
            ),
        )

    def generate_post_media(self, post: RedditPost) -> None:
        """
        Generate audio, image and video clips from the Reddit post.

        Args:
            post (RedditPost): The Reddit post object.
        """

        # Audio
        self.tts.generate_audio_clip(
            post.title,
            language=post.language,
            output_path=post.title_audio_path,
            speaker=self.speaker.name,
            speed=self.audio_speed,
        )

        self.tts.generate_audio_clip(
            post.body,
            language=post.language,
            speaker=self.speaker.name,
            output_path=post.body_audio_path,
            speed=self.audio_speed,
        )

        # We filter None values to deal with post without body text
        post_audios = list(filter(None, [post.title_audio_path, post.body_audio_path]))

        concatenate_audio_files(
            files=post_audios,
            silence_duration=self.silence_duration,
            output_file=post.audio_path,
        )

        # Video
        create_image_videoclip(
            image_path=post.image_path,
            audio_path=post.audio_path,
            output_path=post.video_path,
        )

    def generate_comments_media(self, comments: List[RedditComment]) -> None:
        """
        Generate audio, image and video clips for each comment in the post.

        Args:
            comments (List[RedditComment]): The list of comments to generate media for.
        """

        # Filter comments by length
        for comment in tqdm(comments, desc="Processing comments"):
            try:
                # Video
                create_image_videoclip(
                    image_path=comment.image_path,
                    audio_path=comment.audio_path,
                    output_path=comment.video_path,
                )

            except Exception as e:
                logger.error(f"Error generating comment media: {e}")
                logger.error(f"Error generating comment media: {comment}")
                raise e

    def get_reddit_videos(
        self,
        post: RedditPost,
        comments: List[RedditComment],
        outro_path: str,
    ) -> Tuple[List[str], float]:
        """
        Join all the generated Reddit post and comment videos into a single video.

        Args:
            post (RedditPost): The post to join videos for.
            comments (List[RedditComment]): The comments to join videos for.
            outro_path (str): The path to the outro video.
        """

        videos = (
            [post.video_path]
            + [comment.video_path for comment in comments]
            + [outro_path]
        )

        # Calculate the total duration of the videos to later cut the background video
        # Note that I need to sum the silence seconds duration between each video
        total_duration = sum(
            get_video_duration(video) for video in videos
        ) + self.silence_duration * (len(videos) - 1)

        return videos, total_duration

    def generate_reel_video(
        self,
        post: RedditPost,
        background_video: str,
        reddit_videos: List[str],
        captions: CaptionStyle = None,
        video_text: str = None,
    ) -> None:
        """
        Combine Reddit and Background videos into a single reel video.

        Args:
            post (RedditPost): Reddit post object.
            background_video (str): Path to the background video.
            reddit_videos (List[str]): List of paths to the Reddit videos.
            captions (CaptionStyle): Caption style object. Defaults to None.
                If no captions is provided, no captions will be added.
        """

        # Combine Reddit and Background videos
        overlay_videos(
            background_video=background_video,
            overlay_videos=reddit_videos,
            output_path=self.reel_path.format(post_id=post.post_id, suffix="raw"),
        )

        if captions and video_text:

            # Generate captions
            self.stt.generate_captions(
                input_file=self.reel_path.format(post_id=post.post_id, suffix="raw"),
                text=video_text,
                language=post.language,
                output_file=f"assets/posts/{post.post_id}/reel_raw.ass",
                style=self.captions,
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

        logger.info("Starting Reddit Comments Pipeline...")

        post = get_reddit_object(url)
        logger.info(f"Post retrieved: {post.title}")

        comments = self.get_comments(post, self.remove_duplicates, self.sort_by_score)
        logger.info(f"Retrieved {len(comments)} comments from the post.")

        # Take screenshots
        await self.take_screenshots(post, comments)

        # Generate media for post and comments
        self.generate_post_media(post)
        logger.info(f"Media generated for the post: {post.title}")

        self.generate_comments_media(comments)
        logger.info(f"Media generated for {len(comments)} comments.")

        # Generate media for outro
        outro_path, outro_text = self.generate_outro_media(
            post,
            speaker=self.speaker,
        )
        logger.info(f"Outro media generated at: {outro_path}")

        # Combine reddit videos
        reddit_videos, reddit_video_duration = self.get_reddit_videos(
            post,
            comments,
            outro_path,
        )
        logger.info(f"Combined {len(reddit_videos)} videos into a single reel video.")

        # Generate media for background video
        background_video = self.get_background_video(
            post=post,
            duration=reddit_video_duration,
            video_file=self.background_video_name,
            audio_file=self.background_audio_name,
            video_condition={"topic": "gameplay"},
        )

        logger.info(f"Background video generated at: {background_video}")
        video_text = "\n".join(
            [post.title, post.body]
            + [comment.body for comment in comments]
            + [outro_text],
        )

        with open(f"assets/posts/{post.post_id}/video_text.txt", "w") as f:
            f.write(video_text)

        # Combine all videos
        self.generate_reel_video(
            post=post,
            background_video=background_video,
            reddit_videos=reddit_videos,
            captions=self.captions,
            video_text=video_text if self.captions else None,
        )

        self.save_record(post)


reddit_threads_pipeline = RedditThreadPipeline(
    captions=CaptionStyle(
        fontname="Fira Sans",
        fontsize=22,
        alignment="bottom",
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
