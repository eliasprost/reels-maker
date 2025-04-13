# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod


class VideoPipeline(ABC):
    """
    A base class for creating videos.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description

    @abstractmethod
    def run(self) -> None:
        """
        Method to be implemented by subclasses.
        """
