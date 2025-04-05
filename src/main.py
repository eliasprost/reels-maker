# -*- coding: utf-8 -*-
from loguru import logger

from src.pipelines.videos import RedditCommentsPipeline


def create_video_reddit(link: str):
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

    logger.info("Pipeline initialized, running...")
    pipeline.run(link)


if __name__ == "__main__":
    # parser = argparse.ArgumentParser(description="Run the Reddit Comments Pipeline.")
    # parser.add_argument("link", type=str, help="The link to the Reddit post.", default=None)
    # args = parser.parse_args()

    # while not args.link:
    #     args.link = input("Please enter the link to the Reddit post: ")

    create_video_reddit("hahaha")
