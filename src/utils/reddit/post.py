# -*- coding: utf-8 -*-

import re

import praw
from loguru import logger

from config import settings
from schemas import RedditComment, RedditPost


def parse_comment_permalink(comment: praw.models.Comment, post_id: str) -> str:
    """
    Parse a Reddit comment permalink

    Args:
        comment: praw.models.Comment object
        post_id: Reddit post ID
    """

    [post_id] + ["comment"] + [comment.id] + ["/"]

    return (
        "/".join(comment.permalink.split("/")[:-4])
        + f"/{post_id}/comment/{comment.id}/"
    )


def get_reddit_object(url: str) -> RedditPost:
    """
    Parse a Reddit thread URL to a RedditPost object

    Args:
        url: Reddit thread URL
    """

    if re.match(settings.REDDIT_PATTERN, url):

        reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent="Accessing Reddit threads",
            username=settings.REDDIT_USER_NAME,
            passkey=settings.REDDIT_USER_PASSWORD,
            check_for_async=False,
        )
        thread = reddit.submission(url=url)

        return RedditPost(
            post_id=thread.id,
            title=thread.title,
            body=thread.selftext,
            comments=[
                RedditComment(
                    comment_id=comment.id,
                    post_id=thread.id,
                    body=comment.body,
                    author=comment.author.name,
                    score=comment.score,
                    permalink=parse_comment_permalink(comment, thread.id),
                )
                for comment in thread.comments
                if comment.body != "[deleted]" and comment.author
            ],
            num_comments=thread.num_comments,
            tag=thread.link_flair_text,
            author=thread.author.name,
            score=thread.score,
            permalink=thread.permalink,
        )

    else:
        logger.error(f"Invalid Reddit URL: {url}")
        raise ValueError(f"Invalid Reddit URL: {url}")
