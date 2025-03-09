# -*- coding: utf-8 -*-
import json
import sys
from typing import Any, Dict, List

from tqdm import tqdm

from src.utils.background import download_file, parse_file

# To deal with src path
sys.path.append(".")
sys.path.append("..")


# NOTE:
# This is useful if you want to download all the background media files in a single go and avoid
# downloading them one by one during the reels creation.


def load_json(file_path: str) -> List[Dict[str, Any]]:
    """
    Load a JSON file and return its contents as a list of dictionaries.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        List[Dict[str, Any]]: Parsed JSON data.
    """
    with open(file_path, encoding="utf-8") as file:
        return json.load(file)


def process_files(file_paths: List[Dict[str, Any]]) -> List[str]:
    """
    Parse file paths using `parse_file`.

    Args:
        file_paths (List[Dict[str, Any]]): List of file paths from JSON.

    Returns:
        List[str]: Parsed file paths.
    """
    return [
        parse_file(file)
        for file in tqdm(file_paths, desc="Processing files", unit="file")
    ]


def download_files(files: List[str], file_type: str) -> None:
    """
    Download multiple files using `download_file` with a progress bar.

    Args:
        files (List[str]): List of file paths to download.
        file_type (str): Type of files (e.g., "Audio", "Video") for the tqdm description.
    """
    for file in tqdm(files, desc=f"Downloading {file_type}", unit="file"):
        download_file(file)


if __name__ == "__main__":

    print("Loading JSON data...")
    # Load and process background audios and videos
    audios = process_files(load_json("./data/background_audios.json"))
    videos = process_files(load_json("./data/background_videos.json"))

    print(f"Downloading all background audio files({len(audios)})...")
    download_files(audios, "Audio")

    print(f"Downloading all background video files({len(videos)})...")
    download_files(videos, "Video")
