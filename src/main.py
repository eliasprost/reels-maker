# -*- coding: utf-8 -*-
"""
Interactive CLI for running Reddit video pipelines.
Run `python3 main.py` and follow the prompts.
"""
import asyncio

from loguru import logger

from src.pipelines.reddit_stories import reddit_stories_pipeline
from src.pipelines.reddit_threads import reddit_threads_pipeline
from src.pipelines.schemas import RedditVideoPipeline

# Available pipelines
pipelines = [
    reddit_threads_pipeline,
    reddit_stories_pipeline,
]


async def run_pipeline(link: str, pipeline: RedditVideoPipeline) -> None:
    """
    Execute the specified Reddit video pipeline on the given link.

    Args:
        link (str): URL of the Reddit post or story.
        pipeline (RedditVideoPipeline): The pipeline instance to run.
    """
    try:
        logger.info(f"Starting pipeline '{pipeline.name}'... Please wait.")
        await pipeline.run(link)
        logger.success(f"Pipeline '{pipeline.name}' completed successfully.")
    except Exception as e:
        logger.error(f"Error running pipeline '{pipeline.name}': {e}")


def main():
    """
    Interactive menu: choose a pipeline and enter the Reddit link.
    """
    print("\n=== Reddit Video Pipeline Runner ===\n")
    # List options
    for idx, pipe in enumerate(pipelines, start=1):
        desc = (pipe.description or pipe.__doc__ or "").strip().splitlines()[0]
        print(f"  {idx}) {pipe.name} - {desc}")
    # User selection loop
    while True:
        choice = input("\nSelect a pipeline by number (or 'q' to quit): ").strip()
        if choice.lower() == "q":
            print("Exiting.")
            return
        if not choice.isdigit() or not (1 <= int(choice) <= len(pipelines)):
            print("Invalid selection. Please enter a valid number.")
            continue
        selected = pipelines[int(choice) - 1]
        break

    # Get link from user
    link = input(f"Enter the Reddit URL for '{selected.name}': ").strip()
    print(f"\nRunning '{selected.name}' on {link}\n")

    # Execute
    asyncio.run(run_pipeline(link, selected))


if __name__ == "__main__":
    main()
