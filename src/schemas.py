# -*- coding: utf-8 -*-
import json
import os
import random
from pathlib import Path
from typing import ClassVar, List, Literal, Optional, Tuple

import langid
import yt_dlp
from loguru import logger
from pydantic import BaseModel, field_validator, model_validator
from pysubs2 import Color

from src.utils.path import create_file_folder


class MediaFile(BaseModel):
    title: str
    url: str
    file_name: str
    author: str
    type: Literal["background", "other"] = "other"
    topic: Literal["gameplay", "satisfying", "relaxing", "other"] = "other"
    path: Optional[str] = None

    _file_mapping: ClassVar[dict] = json.load(open("data/file_mapping.json"))

    @property
    def file_type(self) -> str:
        extension = os.path.splitext(self.file_name)[-1].lower().lstrip(".")
        if extension in self._file_mapping.get("audio", []):
            return "audio"
        elif extension in self._file_mapping.get("video", []):
            return "video"
        else:
            raise ValueError(f"File type not supported: {extension}")

    def __init__(self, **data):
        super().__init__(**data)
        if self.path is None:  # If user doesn't provide a path, generate a default one
            self.path = os.path.join(
                "./assets",
                self.type.lower(),
                self.file_type,
                self.topic.lower(),
                self.file_name,
            )

    def download(self):
        """
        Downloads the media file from Youtube. It will take the
        `file_type` from the MediaFile object and download it to
        the corresponding directory and extension.

        Args:
            background (MediaFile): Media file object
        """

        # Check root file path
        root_path = Path(self.path).parent

        # Create directory structure if it doesn't exist
        create_file_folder(self.path)

        if Path(f"{root_path}/{self.file_name}").is_file():
            logger.info(
                f"Media file {self.file_name} already exists. Skipping download.",
            )
            return

        logger.info(f"Downloading {self.file_type} file: {self.file_name}")

        ydl_opts = {
            # We need to remove the file extension for audio files due to the postprocessing
            "outtmpl": str(
                Path(root_path)
                / (
                    self.file_name.split(".")[0]
                    if self.file_type == "audio"
                    else self.file_name
                ),
            ),
            "postprocessors": [],
            "format": "bestaudio/best" if self.file_type == "audio" else "bestvideo",
        }

        if self.file_type == "audio":
            ydl_opts.update(
                {
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": self.file_name.split(".")[-1],
                            "preferredquality": "192",
                        },
                    ],
                },
            )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])

            logger.info(f"Downloaded {self.file_name} successfully")

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Failed to download {self.file_name}: {e}")


class RedditComment(BaseModel):
    comment_id: str
    post_id: str
    body: str
    author: str
    score: int
    permalink: str

    @property
    def length(self) -> int:
        return len(self.body.strip())

    @property
    def image_path(self) -> str:
        return f"assets/posts/{self.post_id}/img/comment_{self.comment_id}.png"

    @property
    def audio_path(self) -> str:
        return f"assets/posts/{self.post_id}/audio/comment_{self.comment_id}.mp3"

    @property
    def video_path(self) -> str:
        return f"assets/posts/{self.post_id}/video/comment_{self.comment_id}.mp4"

    @property
    def url(self) -> str:
        return f"https://www.reddit.com{self.permalink}"


class RedditPost(BaseModel):

    supported_languages: ClassVar[List[str]] = [
        lang["lang_code"] for lang in json.load(open("./data/languages.json"))
    ]

    post_id: str
    title: str
    body: str
    comments: List[RedditComment]
    num_comments: int
    author: str
    score: int
    permalink: str
    tag: Optional[str] = None
    language: Optional[str] = None

    @property
    def length(self) -> int:
        return len(self.title.strip()) + len(self.body.strip())

    @property
    def image_path(self) -> str:
        return f"assets/posts/{self.post_id}/img/post.png"

    @property
    def audio_path(self) -> str:
        return f"assets/posts/{self.post_id}/audio/post.mp3"

    @property
    def video_path(self) -> str:
        return f"assets/posts/{self.post_id}/video/post.mp4"

    @property
    def title_audio_path(self) -> str:
        return f"assets/posts/{self.post_id}/audio/post_title.mp3"

    @property
    def body_audio_path(self) -> str:
        if len(self.body) == 0:
            return None
        return f"assets/posts/{self.post_id}/audio/post_body.mp3"

    @property
    def url(self) -> str:
        return f"https://www.reddit.com{self.permalink}"

    @model_validator(mode="after")
    @classmethod
    def validate_language(cls, model: "RedditPost") -> "RedditPost":
        """
        Validate that the language is in the list of supported languages.
        """

        model.language = langid.classify(model.title + " " + model.body)[0]

        if model.language not in cls.supported_languages:
            raise ValueError(
                f"""
                The language of the post ({model.language}) is not supported, please provide a
                post in one of the following languages: {', '.join(cls.supported_languages)}
                """,
            )
        return model


class Speaker(BaseModel):
    accepted_speakers: ClassVar[dict[str, str]] = {
        "Gitta Nikolina": "female",
        "Narelle Moon": "female",
        "Abrahan Mack": "male",
        "Damien Black": "male",
    }

    name: Optional[str]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """
        Validate that the speaker name is in the list of accepted speakers.
        If no speaker name is provided, a random speaker will be chosen.
        If the speaker name is not in the list of accepted speakers, a ValueError will be raised.

        args:
            value (str): The speaker name.
        """

        if not value:
            value = random.choice(list(cls.accepted_speakers.keys()))

        if value not in cls.accepted_speakers:
            raise ValueError(
                f"""
                Invalid speaker name, please use one of the following:
                {', '.join(cls.accepted_speakers.keys())}
                """,
            )
        return value

    @property
    def id(self) -> str:
        return self.name.replace(" ", "_").lower()

    @property
    def gender(self) -> str:
        return self.accepted_speakers[self.name]


class CaptionStyle(BaseModel):
    """
    Wrapper to handle the V4 style of ASS captions.
    You can add more parameters, using the original name (http://www.tcax.org/docs/ass-specs.htm).

    If you want to add a custom font that is not installed in your system, you need to add it to
    the the project before. Add it to the fonts folder: 'assets/fonts' before.
    """

    fontname: Optional[str] = "Arial"
    fontsize: Optional[int] = 12
    alignment: Optional[Literal["bottom", "middle", "top"]] = "bottom"
    primarycolor: Optional[Tuple[int, int, int, int]] = (197, 241, 79, 1)
    secondarycolor: Optional[Tuple[int, int, int, int]] = (255, 255, 255, 10)
    outlinecolor: Optional[Tuple[int, int, int, int]] = (255, 255, 255, 10)
    backcolor: Optional[Tuple[int, int, int, int]] = (0, 0, 0, 10)
    bold: Optional[bool] = True
    italic: Optional[bool] = False
    outline: Optional[int] = 1
    shadow: Optional[int] = 1

    @model_validator(mode="after")
    @classmethod
    def update_color(cls, model: "CaptionStyle") -> "CaptionStyle":
        """
        Update color parameters to use pysubs2 Color class.
        """
        for field_name, value in model.model_dump().items():
            if "color" in field_name and isinstance(value, (list, tuple)):
                setattr(model, field_name, Color(*value))

        return model

    @model_validator(mode="after")
    @classmethod
    def update_alignment(cls, model: "CaptionStyle") -> "CaptionStyle":
        """
        Update a natural language string to a number for alignment.
        """
        if model.alignment == "bottom":
            model.alignment = 2
        elif model.alignment == "middle":
            model.alignment = 5
        elif model.alignment == "top":
            model.alignment = 8
        else:
            raise ValueError(
                "Invalid alignment value, must be 'bottom', 'middle' or 'top'",
            )

        return model

    model_config = {"extra": "allow"}
