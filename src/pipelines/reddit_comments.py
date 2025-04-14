# -*- coding: utf-8 -*-

import asyncio
import csv
import json
import random
from datetime import datetime
from typing import List, Literal, Tuple

from loguru import logger
from tqdm import tqdm

from src.config import settings
from src.pipelines.indexation import vector_store
from src.pipelines.schemas import VideoPipeline
from src.pipelines.stt import stt_pipeline
from src.pipelines.tts import tts_pipeline
from src.schemas import CaptionStyle, MediaFile, RedditComment, RedditPost, Speaker
from src.utils.media.audio import concatenate_audio_files, cut_audio, get_audio_duration
from src.utils.media.video import (
    add_captions,
    combine_video_with_audio,
    create_image_videoclip,
    cut_video,
    extract_video_thumbnail,
    get_video_duration,
    overlay_videos,
    resize_video,
)
from src.utils.reddit.post import get_reddit_object
from src.utils.reddit.screenshot import take_comment_screenshot, take_post_screenshot


class RedditCommentsPipeline(VideoPipeline):
    """
    A class for creating videos from Reddit post comments.
    """

    def __init__(
        self,
        name: str = "reddit_comments_video_pipeline",
        description: str = "A pipeline for creating videos from Reddit and their comments",
        speaker: str = None,
        theme: Literal["dark", "light"] = "light",
        captions: CaptionStyle = None,
        audio_speed: float = 1.3,
        background_audio_volume: float = 0.20,
        max_comment_length: int = 150,
        silence_duration: float = 0.2,
        background_video: str = None,
        background_audio: str = None,
        remove_duplicates: bool = True,
        sort_by_score: bool = False,
    ) -> None:
        super().__init__(name, description)

        # Transformers text-audio
        self.stt = stt_pipeline
        self.tts = tts_pipeline
        self.vector_store = vector_store

        # Captions
        self.captions = captions
        self.remove_duplicates = remove_duplicates
        self.sort_by_score = sort_by_score

        # Variables
        self.SPEAKER = Speaker(name=speaker)
        self.BACKGROUND_VIDEO_PATH = (
            "assets/posts/{post_id}/video/background_video_{suffix}.mp4"
        )
        self.BACKGROUND_AUDIO_PATH = "assets/posts/{post_id}/audio/background_audio.mp3"
        self.BACKGROUND_AUDIO_VOLUME = background_audio_volume
        self.AUDIO_SPEED = audio_speed
        self.THEME = theme
        self.MAX_COMMENT_LENGTH = max_comment_length
        self.SILENCE_DURATION = silence_duration
        self.BACKGROUND_VIDEO_NAME = background_video
        self.BACKGROUND_AUDIO_NAME = background_audio
        self.REEL_PATH = "assets/posts/{post_id}/reel_{suffix}.mp4"

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
            if comment.length <= self.MAX_COMMENT_LENGTH
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
                speaker=self.SPEAKER.name,
                language=post.language,
                output_path=comment.audio_path,
                speed=self.AUDIO_SPEED,
            )

            duration += get_audio_duration(comment.audio_path)
            processed_comments.append(comment)

            if duration < settings.MIN_VIDEO_DURATION:
                duration += self.SILENCE_DURATION
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
            take_post_screenshot(post, theme=self.THEME),
            *(
                take_comment_screenshot(comment, theme=self.THEME)
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
            speaker=self.SPEAKER.name,
            speed=self.AUDIO_SPEED,
        )

        self.tts.generate_audio_clip(
            post.body,
            language=post.language,
            speaker=self.SPEAKER.name,
            output_path=post.body_audio_path,
            speed=self.AUDIO_SPEED,
        )

        # We filter None values to deal with post without body text
        post_audios = list(filter(None, [post.title_audio_path, post.body_audio_path]))

        concatenate_audio_files(
            files=post_audios,
            silence_duration=self.SILENCE_DURATION,
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

    def generate_outro_media(self, post: RedditPost) -> None:
        """
        Generate outro audio and video clips for the post.

        Args:
            post (RedditPost): The post to generate outro media for.
        """

        outro = [
            lang["outro"]
            for lang in json.load(open("./data/languages.json"))
            if lang["lang_code"] == post.language
        ]

        outro_text = outro[0]

        self.tts.generate_audio_clip(
            text=outro_text,
            language=post.language,
            output_path=f"./assets/others/outros/outro_{post.language}_{self.SPEAKER.id}.mp3",
            speaker=self.SPEAKER.name,
            speed=self.AUDIO_SPEED,
        )

        outro_output_path = (
            f"./assets/others/outros/outro_{post.language}_{self.SPEAKER.id}.mp4"
        )

        create_image_videoclip(
            image_path="./assets/others/outros/outro.png",
            audio_path=f"./assets/others/outros/outro_{post.language}_{self.SPEAKER.id}.mp3",
            output_path=outro_output_path,
        )

        return outro_output_path, outro_text

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
        ) + self.SILENCE_DURATION * (len(videos) - 1)

        return videos, total_duration

    def get_background_video(
        self,
        post: RedditPost,
        duration: float,
        video_file: str = None,
        audio_file: str = None,
    ) -> str:
        """
        Get the background video for the post.

        Args:
            post (RedditPost): The post to get the background video for.
            duration (float): The duration of the background video.
            video_file (str): The name of the background video file name.
                If None, a random background video will be selected.
            audio_file (str): The name of the background audio file name.
                If None, a random background audio will be selected.
        """

        # Get video and audios paths
        videos = [
            MediaFile(**video)
            for video in json.load(open(settings.BACKGROUND_VIDEOS_JSON))
            if MediaFile(**video).type == "background"
            and MediaFile(**video).topic == "gameplay"
        ]

        audios = [
            MediaFile(**audio)
            for audio in json.load(open(settings.BACKGROUND_AUDIOS_JSON))
            if MediaFile(**audio).type == "background"
        ]

        video = next(
            (video for video in videos if video.file_name == video_file),
            random.choice(videos),
        )
        audio = next(
            (audio for audio in audios if audio.file_name == audio_file),
            random.choice(audios),
        )

        # Download the files if they are not already downloaded
        video.download()
        audio.download()

        # Audio
        cut_audio(
            input_path=audio.path,
            output_path=self.BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
            duration=duration,
            fade_duration=1,
        )

        # Video
        cut_video(
            input_path=video.path,
            output_path=self.BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="cutted",
            ),
            duration=duration,
        )

        resize_video(
            input_path=self.BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="cutted",
            ),
            output_path=self.BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="cutted_croped",
            ),
            height=settings.SCREEN_HEIGHT,
            width=settings.SCREEN_WIDTH,
            zoom_crop=True,
        )

        # Combine background video and audio
        combine_video_with_audio(
            video_path=self.BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="cutted_croped",
            ),
            audio_path=self.BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
            output_path=self.BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="finished",
            ),
            volume=self.BACKGROUND_AUDIO_VOLUME,
        )

        return self.BACKGROUND_VIDEO_PATH.format(
            post_id=post.post_id,
            suffix="finished",
        )

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
            output_path=self.REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        )

        if captions and video_text:

            # Generate captions
            self.stt.generate_captions(
                input_file=self.REEL_PATH.format(post_id=post.post_id, suffix="raw"),
                text=video_text,
                language=post.language,
                output_file=f"assets/posts/{post.post_id}/reel_raw.ass",
                style=self.captions,
            )

            # Add subtitle to video
            add_captions(
                input_file=self.REEL_PATH.format(post_id=post.post_id, suffix="raw"),
                output_file=self.REEL_PATH.format(
                    post_id=post.post_id,
                    suffix="subtitled",
                ),
                caption_path=f"assets/posts/{post.post_id}/reel_raw.ass",
                font_path=self.captions.font_path,
            )

        extract_video_thumbnail(
            video_path=self.REEL_PATH.format(
                post_id=post.post_id,
                suffix="subtitled" if captions else "raw",
            ),
            output_path=f"assets/posts/{post.post_id}/thumbnail.png",
        )

        logger.info(f"Video created for post {post.post_id}")

    def save_record(self, post: RedditPost) -> None:
        """
        Save the record of the processed video to a CSV file.

        Args:
            post (RedditPost): The Reddit post object.
        """

        with open(settings.PROCESSED_VIDEOS_CSV, "a", newline="") as csvfile:
            fieldnames = ["post_id", "title", "url", "timestamp"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write header if the file is empty
            if csvfile.tell() == 0:
                writer.writeheader()

            writer.writerow(
                {
                    "post_id": post.post_id,
                    "title": post.title,
                    "url": post.url,
                    "timestamp": datetime.now().strftime("%Y-%m-%d:%H:%M:%S"),
                },
            )

            logger.info(f"Record saved for post {post.post_id}")

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
        outro_path, outro_text = self.generate_outro_media(post)

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
            video_file=self.BACKGROUND_VIDEO_NAME,
            audio_file=self.BACKGROUND_AUDIO_NAME,
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


reddit_comments_pipeline = RedditCommentsPipeline(
    captions=CaptionStyle(
        fontname="Fira Sans",
        fontsize=14,
        alignment="bottom",
        marginv=40,
    ),
)
