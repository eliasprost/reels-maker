# -*- coding: utf-8 -*-
import csv
import json
import random
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from src.config import settings
from src.pipelines.indexation import vector_store
from src.pipelines.stt import stt_pipeline
from src.pipelines.tts import tts_pipeline
from src.schemas import CaptionStyle, MediaFile, RedditPost, Speaker
from src.utils.media.audio import cut_audio
from src.utils.media.video import (
    combine_video_with_audio,
    create_image_videoclip,
    cut_video,
    resize_video,
)


class RedditVideoPipeline(ABC):
    """
    A base class for creating videos.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        speaker: Optional[str] = None,
        captions: Optional[CaptionStyle] = None,
        background_video_name: Optional[str] = None,
        background_audio_name: Optional[str] = None,
        background_audio_volume: float = 0.20,
    ) -> None:
        self.name = name
        self.description = description
        self.speaker = Speaker(name=speaker)
        self.captions = captions
        self.background_video_name = background_video_name
        self.background_audio_name = background_audio_name
        self.background_audio_volume = background_audio_volume

        # Transformers text-audio
        self.stt = stt_pipeline
        self.tts = tts_pipeline
        self.vector_store = vector_store

    def generate_outro_media(
        self,
        post: RedditPost,
        audio_speed: float,
        speaker: Speaker,
    ) -> None:
        """
        Generate outro audio and video clips for the post.

        Args:
            post (RedditPost): The post to generate outro media for.
            audio_speed (float): The speed of the audio.
            speaker (Speaker): The speaker to use for the audio.
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
            output_path=f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp3",
            speaker=speaker.name,
            speed=audio_speed,
        )

        outro_output_path = (
            f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp4"
        )

        create_image_videoclip(
            image_path="./assets/others/outros/outro.png",
            audio_path=f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp3",
            output_path=outro_output_path,
        )

        return outro_output_path, outro_text

    def get_background_video(
        self,
        post: RedditPost,
        duration: float,
        video_file: str = None,
        audio_file: str = None,
        video_condition: Dict[str, Any] = None,
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
            video_condition (Dict[str, Any]): The condition to filter the background videos.
                If None, no condition will be applied. Example: {"topic": "gameplay"}
        """

        if video_condition:
            videos = [
                MediaFile(**video)
                for video in json.load(open(settings.BACKGROUND_VIDEOS_JSON))
                if MediaFile(**video).type == "background"
                and all(
                    getattr(MediaFile(**video), key) == value
                    for key, value in video_condition.items()
                )
            ]

        else:
            videos = [
                MediaFile(**video)
                for video in json.load(open(settings.BACKGROUND_VIDEOS_JSON))
                if MediaFile(**video).type == "background"
            ]

        audios = [
            MediaFile(**audio)
            for audio in json.load(open(settings.BACKGROUND_AUDIOS_JSON))
            if MediaFile(**audio).type == "background"
        ]

        # Select specific video and audio files if provided, otherwise select random ones
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
            output_path=self.background_audio_path.format(post_id=post.post_id),
            duration=duration,
            fade_duration=1,
        )

        # Video
        cut_video(
            input_path=video.path,
            output_path=self.background_video_path.format(
                post_id=post.post_id,
                suffix="cutted",
            ),
            duration=duration,
        )

        resize_video(
            input_path=self.background_video_path.format(
                post_id=post.post_id,
                suffix="cutted",
            ),
            output_path=self.background_video_path.format(
                post_id=post.post_id,
                suffix="cutted_croped",
            ),
            height=settings.SCREEN_HEIGHT,
            width=settings.SCREEN_WIDTH,
            zoom_crop=True,
        )

        # Combine background video and audio
        combine_video_with_audio(
            video_path=self.background_video_path.format(
                post_id=post.post_id,
                suffix="cutted_croped",
            ),
            audio_path=self.background_audio_path.format(post_id=post.post_id),
            output_path=self.background_video_path.format(
                post_id=post.post_id,
                suffix="finished",
            ),
            volume=self.background_audio_volume,
        )

        return self.background_video_path.format(
            post_id=post.post_id,
            suffix="finished",
        )

    def save_record(self, post: RedditPost) -> None:
        """
        Save the record of the processed video to a CSV file.

        Args:
            post (RedditPost): The Reddit post object.
        """

        with open(settings.PROCESSED_VIDEOS_CSV, "a", newline="") as csvfile:
            fieldnames = ["post_id", "title", "url", "timestamp", "pipeline"]
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
                    "pipeline": self.name,
                },
            )

            logger.info(f"Record saved for post {post.post_id}")

    @abstractmethod
    def generate_reel_video(self) -> None:
        """
        Method to be implemented by subclasses.
        """

    @abstractmethod
    def run(self) -> None:
        """
        Method to be implemented by subclasses.
        """
