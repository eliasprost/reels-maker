# -*- coding: utf-8 -*-
from pathlib import Path

import torch
from loguru import logger

from src.config import settings


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


def get_device() -> str:
    """
    Get the device to use for PyTorch operations.
    """
    if settings.FORCE_HF_CPU:
        return "cpu"
    elif torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"
