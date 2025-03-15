# -*- coding: utf-8 -*-
import json
import os
from typing import Literal, Tuple

from loguru import logger
from PIL import Image
from playwright.async_api import Browser, BrowserContext, async_playwright

from src.config import settings
from src.schemas import RedditComment, RedditPost


async def login_reddit(context: BrowserContext, timeout: int = 5000) -> BrowserContext:
    """
    Login to Reddit

    Args:
        context: Playwright context
        timeout: Timeout in milliseconds. Default is 5000
    """

    try:
        page = await context.new_page()
        await page.goto("https://www.reddit.com/login", timeout=0)
        await page.set_viewport_size(
            {"width": settings.SCREEN_WIDTH, "height": settings.SCREEN_HEIGHT},
        )
        await page.wait_for_load_state()

        await page.locator('input[name="username"]').fill(settings.REDDIT_USER_NAME)
        await page.locator('input[name="password"]').fill(
            settings.REDDIT_USER_PASSWORD,
        )
        await page.get_by_role("button", name="Log In").click()
        await page.wait_for_timeout(timeout)

        logger.info(
            f"Logged in to Reddit using the username: {settings.REDDIT_USER_NAME}",
        )

    except Exception as e:
        page = None

        logger.error(f"Error logging in to Reddit: {e}")

    return page


async def build_browser_context(
    playwright_instance: async_playwright,
    url: str,
    theme: Literal["dark", "Light"] = "light",
    timeout: int = 5000,
) -> Tuple[BrowserContext, Browser]:
    """
    Build a Playwright browser context

    Args:
        playwright_instance: Playwright instance
        url: Reddit URL, can we a post or a comment
        cookie_file_path: Path to the cookie file. Default is "./data/cookies/cookie-dark-mode.json"
        timeout: Timeout in milliseconds. Default is 5000
    """

    browser = await playwright_instance.chromium.launch(headless=True)

    # Cookies
    cookie_file = open(f"./data/cookies/cookie-{theme}-mode.json", encoding="utf-8")
    dsf = (settings.SCREEN_WIDTH // 600) + 1

    context = await browser.new_context(
        locale="en-us",
        color_scheme=theme,
        viewport={"width": settings.SCREEN_WIDTH, "height": settings.SCREEN_HEIGHT},
        device_scale_factor=dsf,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",  # noqa: E501
    )

    cookies = json.load(cookie_file)
    cookie_file.close()

    await context.add_cookies(cookies)  # load preference cookies

    # Login to Reddit
    page = await login_reddit(context)

    # Open Reddit thread
    await page.goto(url, timeout=0)
    await page.set_viewport_size(
        {"width": settings.SCREEN_WIDTH, "height": settings.SCREEN_HEIGHT},
    )
    await page.wait_for_load_state()
    await page.wait_for_timeout(timeout)

    # Scroll to the bottom of the page
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(timeout)

    logger.info(f"Opened Reddit url: {url}")

    return page, browser


async def take_post_screenshot(
    post: RedditPost,
    theme: Literal["dark", "light"] = "light",
) -> None:
    """
    Take and save a screenshot of the main post in a Reddit post/thread

    Args:
        post: RedditPost object
    """

    # Check if file exists
    if os.path.exists(post.image_path):
        logger.info(f"Main post screenshot already exists: {post.image_path}")
        return

    async with async_playwright() as p:
        context, browser = await build_browser_context(p, theme=theme, url=post.url)
        await context.locator("shreddit-post").screenshot(path=post.image_path)
        logger.info(f"Main post screenshot saved to: {post.image_path}")
        await browser.close()


def join_images_vertically(image_paths: list, output_path: str) -> None:
    """
    Combine multiple images vertically into a single image.

    Args:
        image_paths (list): List of image file paths to combine.
        output_path (str): Path to save the combined image.
    """
    images = [Image.open(path) for path in image_paths]
    total_height = sum(img.height for img in images)
    min_width = min(img.width for img in images)

    combined_image = Image.new("RGB", (min_width, total_height))

    y_offset = 0
    for img in images:
        combined_image.paste(img, (0, y_offset))
        y_offset += img.height

    combined_image.save(output_path)
    logger.info(f"Combined image saved to: {output_path}")


async def take_comment_screenshot(
    comment: RedditComment,
    theme: Literal["dark", "light"] = "light",
) -> None:
    """
    Take and save a screenshot of a comment, EXCLUDING replies.

    Args:
        comment: RedditComment object
    """

    if os.path.exists(comment.image_path):
        logger.info(f"Comment screenshot already exists: {comment.image_path}")
        return

    async with async_playwright() as p:
        page, browser = await build_browser_context(p, theme=theme, url=comment.url)

        # Locate the target comment elements
        comment_header = page.get_by_label(
            f"Metadata for {comment.author}'s comment",
        ).first
        comment_content = page.locator(
            'div[class="md text-14 rounded-[8px] pb-2xs overflow-hidden"][slot="comment"]',
        ).first
        action_row = page.locator(
            f'shreddit-comment-action-row[slot="actionRow"][permalink="{comment.permalink}"]',
        ).first

        # Take individual screenshots
        header_path = comment.image_path.replace(".png", "_header.png")
        content_path = comment.image_path.replace(".png", "_content.png")
        action_row_path = comment.image_path.replace(".png", "_action_row.png")

        await comment_header.screenshot(path=header_path)
        await comment_content.screenshot(path=content_path)
        await action_row.screenshot(path=action_row_path)

        # Combine the screenshots vertically
        join_images_vertically(
            [header_path, content_path, action_row_path],
            comment.image_path,
        )

        # Remove part files if they exist
        for path in [header_path, content_path, action_row_path]:
            if os.path.exists(path):
                os.remove(path)

        await browser.close()
