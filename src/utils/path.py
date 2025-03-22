# -*- coding: utf-8 -*-
from pathlib import Path
from typing import List

from loguru import logger


def create_file_folder(file_path: str) -> None:
    """
    Creates parent folder of a given input path if it doesn't exist.

    Args:
        file_path (str): The path to the file.
    """
    path = Path(file_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Folder not found. Created folder: {path.parent}")
    else:
        logger.info(f"Folder already exists: {path.parent}")


def get_folder_files(directory: str, extension: str) -> List[str]:
    """
    Get all files with a specific extension from a directory.

    Args:
        directory (str): The directory to search.
        extension (str): The file extension to filter by.
    """
    return [f.name for f in directory.glob(f"*.{extension}")]
