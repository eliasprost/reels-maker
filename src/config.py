# -*- coding: utf-8 -*-
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    This class defines the settings for the application. The settings are
    loaded from the environment files specified in the Config class: .env

    Documentation:
    - https://docs.pydantic.dev/latest/concepts/pydantic_settings/

    Attributes:
    - MIN_VIDEO_DURATION: The minimum duration of the video in seconds.
    - REDDIT_CLIENT_ID: The client ID of the Reddit application.
    - REDDIT_CLIENT_SECRET: The client secret of the Reddit application.
    - REDDIT_USER_NAME: The username of the Reddit user.
    - REDDIT_USER_PASSWORD: The password of the Reddit user.
    - SCREEN_HEIGHT: The height of the screen in pixels.
    - SCREEN_WIDTH: The width of the screen in pixels.
    - PYTHONWARNINGS: The warnings to be ignored.
    - TOKENIZERS_PARALLELISM: The parallelism of the tokenizers.
    """

    # Main video settings
    MIN_VIDEO_DURATION: float = 70.0

    # Reddit
    REDDIT_CLIENT_ID: str
    REDDIT_CLIENT_SECRET: str
    REDDIT_USER_NAME: str
    REDDIT_USER_PASSWORD: str

    # Screen
    SCREEN_HEIGHT: int = 1920
    SCREEN_WIDTH: int = 1080

    # Others
    PYTHONWARNINGS: str = "ignore"
    TOKENIZERS_PARALLELISM: str = "true"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
