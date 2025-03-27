# -*- coding: utf-8 -*-

import praw

from src.schemas import RedditComment, RedditPost


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


def parse_reddit_post(thread: praw.models.Submission) -> RedditPost:
    """
    Parse a Reddit thread to a RedditPost object

    Args:
        thread: praw.models.Submission
    """

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
