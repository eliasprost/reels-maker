# -*- coding: utf-8 -*-

from pathlib import Path

import yt_dlp
from loguru import logger

from src.schemas import BackgroundFile

BACKGROUND_ROOT_PATH = "./assets/background/{type}"


def parse_file(data: dict) -> BackgroundFile:
    """
    Parse a background file into a BackgroundFile

    Args:
        data (dict): Background file data
    """

    return BackgroundFile(
        title=data["title"],
        url=data["url"],
        file_name=data["file_name"],
        author=data["author"],
    )


def download_file(file: BackgroundFile):
    """
    Downloads the background/s file from Youtube. It will take the
    `file_type` from the BackgroundFile object and download it to
    the corresponding directory and extension.

    Args:
        background (BackgroundFile): Background file
    """

    root_path = BACKGROUND_ROOT_PATH.format(type=file.file_type)

    if not Path(root_path).exists():
        Path(root_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Creating the {root_path} directory")

    if Path(f"{root_path}/{file.file_name}").is_file():
        logger.info(
            f"Background audio {file.file_name} already exists. Skipping download.",
        )
        return

    logger.info(f"Downloading background {file.file_type}: {file.file_name}")

    ydl_opts = {
        # We need to remove the file extension for audio files due to the postprocessing
        "outtmpl": str(
            Path(root_path)
            / (
                file.file_name.split(".")[0]
                if file.file_type == "audio"
                else file.file_name
            ),
        ),
        "postprocessors": [],
        "format": "bestaudio/best" if file.file_type == "audio" else "bestvideo",
    }

    if file.file_type == "audio":
        ydl_opts.update(
            {
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": file.file_name.split(".")[-1],
                        "preferredquality": "192",
                    },
                ],
            },
        )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([file.url])
