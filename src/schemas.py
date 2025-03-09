# -*- coding: utf-8 -*-
import json
from typing import List

from pydantic import BaseModel


class BackgroundFile(BaseModel):
    title: str
    url: str
    file_name: str
    author: str

    @property
    def file_type(self) -> str:
        types = json.load(open("data/file_mapping.json"))
        if self.file_name.split(".")[-1] in types["audio"]:
            return "audio"
        elif self.file_name.split(".")[-1] in types["video"]:
            return "video"
        else:
            raise ValueError(
                f"File type not supported: {self.file_name.split('.')[-1]}",
            )


class RedditComment(BaseModel):
    comment_id: str
    post_id: str
    body: str
    author: str
    score: int
    permalink: str

    @property
    def lenght(self) -> int:
        return len(self.body.split())

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
    post_id: str
    title: str
    body: str
    comments: List[RedditComment]
    num_comments: int
    tag: str
    author: str
    score: int
    permalink: str

    @property
    def lenght(self) -> int:
        return len(self.title.split()) + len(self.body.split())

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
        return f"assets/posts/{self.post_id}/audio/post_body.mp3"

    @property
    def url(self) -> str:
        return f"https://www.reddit.com{self.permalink}"
