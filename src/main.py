# -*- coding: utf-8 -*-
import argparse
import asyncio

from loguru import logger

from src.pipelines.videos import RedditCommentsPipeline


async def create_video_reddit(link: str):
    """
    Main function to run the Reddit Comments Pipeline.

    Args:
       link (str): The link to the Reddit post.
    """

    try:
        logger.info("Starting the Reddit Comments Pipeline, please wait...")
        pipeline = RedditCommentsPipeline()

    except Exception as e:
        logger.error(f"Error initializing pipeline: {e}")
        return

    await pipeline.run(link)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Reddit Comments Pipeline.")
    parser.add_argument(
        "--link",
        type=str,
        required=True,
        help="The link to the Reddit post.",
    )
    args = parser.parse_args()

    asyncio.run(create_video_reddit(args.link))
