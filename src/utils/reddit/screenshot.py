# -*- coding: utf-8 -*-
import json
import os
from typing import List, Literal, Tuple

from loguru import logger
from PIL import Image
from playwright.async_api import Browser, BrowserContext, TimeoutError, async_playwright

from src.config import settings
from src.schemas import RedditComment


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
        theme: "light" or "dark" mode
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


async def take_post_screenshot(
    post,
    elements: List[
        Literal["header", "title", "content", "action_row"]
    ] = [  # noqa: B006
        "header",
        "title",
        "content",
        "action_row",
    ],
    theme: Literal["dark", "light"] = "light",
    timeout: int = 5000,
) -> None:
    """
    Take and save a screenshot of the main post in a Reddit post/thread.

    Args:
        post: RedditPost object
        elements: List of elements to include in the screenshot
        theme: "light" or "dark" mode
        timeout: Timeout in milliseconds. Default is 5000
    """

    if os.path.exists(post.image_path):
        logger.info(f"Post screenshot already exists: {post.image_path}")
        return

    async with async_playwright() as p:
        page, browser = await build_browser_context(p, theme=theme, url=post.url)

        # Locate elements
        header = page.locator('div[slot="credit-bar"]').first  # noqa: F841
        title = page.locator('h1[slot="title"]').first  # noqa: F841

        try:
            content = page.locator(  # noqa: F841
                'div[class="text-neutral-content"][slot="text-body"]',
            ).first
        except TimeoutError:
            logger.info("The post content is inexistent or not visible.")

        action_row = page.locator(  # noqa: F841
            'div[class="shreddit-post-container flex gap-sm flex-row items-center flex-nowrap justify-start h-2xl mt-md px-md xs:px-0"]',  # noqa: E501
        ).first

        # Take screenshots
        screenshots = []
        for element in elements:
            path = post.image_path.replace(".png", f"_{element}.png")
            locator = eval(element)
            if locator:
                await locator.screenshot(path=path)
                screenshots.append(path)

        if screenshots:
            # Combine the screenshots vertically
            join_images_vertically(screenshots, post.image_path)

            # Remove part files
            for path in screenshots:
                if os.path.exists(path):
                    os.remove(path)

            logger.info(f"Post screenshot saved to: {post.image_path}")

        await browser.close()


async def take_comment_screenshot(
    comment: RedditComment,
    elements: List[Literal["header", "content", "action_row"]] = [  # noqa: B006
        "header",
        "content",
        "action_row",
    ],  # noqa: B006
    theme: Literal["dark", "light"] = "light",
    timeout: int = 5000,
) -> None:
    """
    Take and save a screenshot of a comment, EXCLUDING replies.

    Args:
        comment: RedditComment object
        elements: List of elements to include in the screenshot
        theme: "light" or "dark" mode
        timeout: Timeout in milliseconds. Default is 5000
    """

    if os.path.exists(comment.image_path):
        logger.info(f"Comment screenshot already exists: {comment.image_path}")
        return

    async with async_playwright() as p:
        page, browser = await build_browser_context(p, theme=theme, url=comment.url)

        # Locate the target comment elements
        header = page.get_by_label(
            f"Metadata for {comment.author}'s comment",
        ).first

        # Attempt to locate the content and action row within the specified timeout
        # This is to deal with not fully displayed comments
        try:
            content = await page.wait_for_selector(  # noqa: F841
                'div[class="md text-14 rounded-[8px] pb-2xs overflow-hidden"][slot="comment"]',
                timeout=timeout,
            )
            action_row = await page.wait_for_selector(  # noqa: F841
                f'shreddit-comment-action-row[slot="actionRow"][permalink="{comment.permalink}"]',
                timeout=timeout,
            )

        except TimeoutError:
            logger.info("Comment content not visible, clicking header to expand.")
            await header.click()

            # Retry locating the content and action row after expanding
            content = await page.wait_for_selector(  # noqa: F841
                'div[class="md text-14 rounded-[8px] pb-2xs overflow-hidden"][slot="comment"]',
                timeout=timeout,
            )
            action_row = await page.wait_for_selector(  # noqa: F841
                f'shreddit-comment-action-row[slot="actionRow"][permalink="{comment.permalink}"]',
                timeout=timeout,
            )

        # Take screenshots
        screenshots = []
        for element in elements:
            path = comment.image_path.replace(".png", f"_{element}.png")
            await eval(element).screenshot(path=path)
            screenshots.append(path)

        # Combine the screenshots vertically
        join_images_vertically(
            screenshots,
            comment.image_path,
        )

        # Remove part files if they exist
        for path in screenshots:
            if os.path.exists(path):
                os.remove(path)

        await browser.close()
