# -*- coding: utf-8 -*-

import json
from typing import List

from tqdm import tqdm

from src.config import settings
from src.schemas import MediaFile

# NOTE:
# This is useful if you want to download all the background media files in a single go and avoid
# downloading them one by one during the reels creation.


def download_media_files(files: List[str], file_type: str) -> None:
    """
    Download multiple files using `download_media_file` with a progress bar.

    Args:
        files (List[str]): List of file paths to download.
        file_type (str): Type of files (e.g., "Audio", "Video") for the tqdm description.
    """
    for file in tqdm(files, desc=f"Downloading {file_type}", unit="file"):
        file.download()


if __name__ == "__main__":

    print("Loading JSON data...")
    # Load and process background audios and videos
    audios = [
        MediaFile(**audio) for audio in json.load(open(settings.BACKGROUND_AUDIOS_JSON))
    ]
    videos = [
        MediaFile(**video) for video in json.load(open(settings.BACKGROUND_VIDEOS_JSON))
    ]

    print(f"Downloading all background audio files({len(audios)})...")
    download_media_files(audios, "Audio")

    print(f"Downloading all background video files({len(videos)})...")
    download_media_files(videos, "Video")
