# -*- coding: utf-8 -*-
import asyncio
import json
import random
import re
import subprocess

import pandas as pd
import praw
import streamlit as st

from config import settings
from schemas import MediaFile, Speaker
from utils.media.audio import concatenate_audio_files, cut_audio, get_audio_duration
from utils.media.video import (
    add_captions,
    combine_video_with_audio,
    create_image_videoclip,
    cut_video,
    extract_video_thumbnail,
    get_video_duration,
    overlay_videos,
    resize_video,
)
from utils.reddit.post import get_reddit_object
from utils.reddit.screenshot import take_comment_screenshot, take_post_screenshot
from utils.stt import get_speech_to_text
from utils.tts import get_text_to_speech

# Initialize session state
if "selected_video" not in st.session_state:
    st.session_state.selected_video = None
if "selected_audio" not in st.session_state:
    st.session_state.selected_audio = None
if "selected_comments" not in st.session_state:
    st.session_state.selected_comments = []
if "continue_to_reddit_videos" not in st.session_state:
    st.session_state.continue_to_reddit_videos = False
if "continue_to_background_video" not in st.session_state:
    st.session_state.continue_to_background_video = False
if "continue_to_cut" not in st.session_state:
    st.session_state.continue_to_cut = False
if "continue_to_video_combining" not in st.session_state:
    st.session_state.continue_to_video_combining = False

# Main streamlit UI params
st.set_page_config(page_title="Reddit Video Generator", layout="wide")

tts = get_text_to_speech()
stt = get_speech_to_text()

# Sidebar
st.sidebar.header("Settings")
BACKGROUND_VIDEO_PATH = "assets/posts/{post_id}/video/background_video_{suffix}.mp4"
BACKGROUND_AUDIO_PATH = "assets/posts/{post_id}/audio/background_audio.mp3"
MIN_VIDEO_DURATION = st.sidebar.number_input(
    "Minimum Video Duration (s)",
    min_value=10.0,
    value=settings.MIN_VIDEO_DURATION,
    step=5.0,
)
SCREEN_HEIGHT = st.sidebar.number_input(
    "Screen Height",
    min_value=720,
    value=settings.SCREEN_HEIGHT,
    step=10,
)
SCREEN_WIDTH = st.sidebar.number_input(
    "Screen Width",
    min_value=720,
    value=settings.SCREEN_WIDTH,
    step=10,
)
SPEAKER = st.sidebar.selectbox("Speaker", options=Speaker.accepted_speakers.keys())
AUDIO_SPEED = st.sidebar.number_input("Audio Speed", min_value=0.5, value=1.3, step=0.1)
BACKGROUND_AUDIO_VOLUME = st.sidebar.number_input(
    "Background Audio Volume",
    min_value=0.0,
    value=0.15,
    step=0.01,
)
THEME = st.sidebar.selectbox("Theme", options=["light", "dark"])
REEL_PATH = "assets/posts/{post_id}/reel_{suffix}.mp4"

preset_options = ["veryslow", "slow", "medium", "fast", "veryfast"]
PRESET = st.sidebar.selectbox(
    "Preset",
    options=preset_options,
    index=preset_options.index(settings.PRESET),
)

ADD_CAPTIONS = st.sidebar.checkbox("Add Captions", value=True)

# Main UI
st.title("Reddit Video Generator")

# Step 1 - Reddit post
st.header("1 - Reddit post")
REDDIT_URL = st.text_input("Enter a Reddit Post URL:")

valid_url = re.match(r"^https://www\.reddit\.com/.*", REDDIT_URL)

if valid_url:
    st.success("Valid Reddit URL!")

    # Get post data
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent="Accessing Reddit threads",
        username=settings.REDDIT_USER_NAME,
        passkey=settings.REDDIT_USER_PASSWORD,
        check_for_async=False,
    )

    try:
        post = get_reddit_object(reddit.REDDIT_URL)

    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

    # Show post data
    with st.expander("Post data", expanded=False):
        st.json(post.model_dump())

else:
    post = None
    if REDDIT_URL:
        st.error("Invalid URL. Please enter a valid Reddit post link.")

# Only show Step 2 if Step 1 is completed
if post is not None:
    st.header("2 - Comments")
    st.write("Select video content")

    speaker = Speaker(name=SPEAKER)
    col1, col2 = st.columns(2)
    with col1:
        max_comment_length = st.number_input(
            "Max comment length",
            min_value=1,
            max_value=1000,
            value=150,
        )
    with col2:
        comments_to_show = (
            st.number_input("Comments to show", min_value=5, max_value=100, value=25)
            + 1
        )

    with st.spinner("Generating post audio clip"):
        tts.generate_audio_clip(
            post.title,
            language=post.language,
            output_path=post.title_audio_path,
            speaker=speaker.name,
            speed=AUDIO_SPEED,
        )
        tts.generate_audio_clip(
            post.body,
            language=post.language,
            speaker=speaker.name,
            output_path=post.body_audio_path,
            speed=AUDIO_SPEED,
        )

        # We filter None values to deal with post without body text
        post_audios = list(filter(None, [post.title_audio_path, post.body_audio_path]))

        concatenate_audio_files(
            files=post_audios,
            silence_duration=0.2,
            output_file=post.audio_path,
        )

    st.write("**Post title**")
    st.info(post.title)

    if post.body:
        st.write("**Post body**")
        st.info(post.body)

    with st.expander("Preview post audio", expanded=False):
        st.audio(post.audio_path)

    post_audio_duration = get_audio_duration(post.audio_path)

    # Check if comments_to_show or max_comment_length has changed
    if (
        "comments_to_show" not in st.session_state
        or "max_comment_length" not in st.session_state
        or st.session_state.comments_to_show != comments_to_show
        or st.session_state.max_comment_length != max_comment_length
    ):

        # Regenerate the DataFrame if the inputs have changed
        progress_text = "Generating comment audio clips..."
        progress_bar = st.progress(0, text=progress_text)

        data = []
        for i, comment in enumerate(post.comments[:comments_to_show]):
            if (
                comment.length <= max_comment_length
                and comment.body != "[removed]"
                and comment.author != "deleted"
            ):
                data.append(
                    {
                        "comment_id": comment.comment_id,
                        "body": comment.body,
                        "score": comment.score,
                        "length": comment.length,
                        "url": comment.url,
                        "image_path": comment.image_path,
                        "audio_path": comment.audio_path,
                        "select": False,
                    },
                )

                tts.generate_audio_clip(
                    comment.body,
                    speaker=speaker.name,
                    language=post.language,
                    output_path=comment.audio_path,
                    speed=AUDIO_SPEED,
                )

            # Update progress bar
            progress = (i + 1) / comments_to_show
            progress_bar.progress(progress, text=progress_text)

        # Convert the data to a DataFrame
        df = pd.DataFrame(data)

        # Add clip duration
        df["clip_duration"] = df["audio_path"].apply(lambda x: get_audio_duration(x))

        # Sort comments by score (or any other metric) in descending order
        df = df.sort_values(by="score", ascending=False)

        # Automatically select comments until MIN_VIDEO_DURATION is reached (with post audio)
        total_duration = 0
        for idx, row in df.iterrows():
            if total_duration >= MIN_VIDEO_DURATION - post_audio_duration:
                break
            df.at[idx, "select"] = True
            total_duration += row["clip_duration"]

        # Store the DataFrame and input values in session state
        st.session_state.df = df
        st.session_state.comments_to_show = comments_to_show
        st.session_state.max_comment_length = max_comment_length

    # Retrieve the DataFrame from session state
    df = st.session_state.df

    # Display the table with checkboxes using st.data_editor
    st.write("### Select Comments")

    # Use st.data_editor to allow checkbox selection
    edited_df = st.data_editor(
        df,
        column_config={
            "select": st.column_config.CheckboxColumn("select", default=True),
        },
        hide_index=True,
    )

    # Update the selected comments in session state
    st.session_state.selected_comments = edited_df[edited_df["select"]]

    # Expander to visualize the selected comments audios
    with st.expander("Preview selected comments", expanded=False):
        for _, row in st.session_state.selected_comments.iterrows():
            st.info(f"{row['body']}", icon="💬")
            st.write(f"**Duration**: `{row['clip_duration']}`")
            st.audio(row["audio_path"], format="audio/wav")
            st.write("---")

    # Display the number of selected comments and total duration
    st.write(
        f"**Number of selected comments**: {len(st.session_state.selected_comments)}",
    )

    st.write(f"**Post audio duration**: {post_audio_duration} s")

    total_comments_duration = round(
        st.session_state.selected_comments["clip_duration"].sum(),
        2,
    )
    st.write(
        f""""
        **Comments duration**: {
            round(st.session_state.selected_comments['clip_duration'].sum(), 2)
        } s
        """,
    )

    total_audio_duration = round(post_audio_duration + total_comments_duration, 2)
    st.write(f"**Total audio duration**: {total_audio_duration} s")

    if not total_audio_duration >= MIN_VIDEO_DURATION:
        st.warning(
            f"You need to select **more comments** to have more than {MIN_VIDEO_DURATION} s",
        )

    if st.button("Continue to the Reddit videoclips creation"):
        st.session_state.continue_to_reddit_videos = True

# Only show Step 3 if Step 2 is completed
if post is not None and st.session_state.continue_to_reddit_videos:
    st.header("3 - Create reddit post videos")

    try:
        with st.spinner("(1/2) Logging in and taking post screenshot..."):
            # Take post screenshot and mount post video
            asyncio.run(take_post_screenshot(post, THEME))

        with st.spinner("(2/2) Generating post videocplip..."):
            # Generate post video: combine audio and image
            create_image_videoclip(
                image_path=post.image_path,
                audio_path=post.audio_path,
                output_path=post.video_path,
            )

        # Take comment screenshot and mount comments videos
        comments_progress_bar = st.progress(0, text="Generating comments videoclips...")
        comments_to_process = [
            comment
            for comment in post.comments
            if comment.comment_id
            in st.session_state.selected_comments["comment_id"].to_list()
        ]
        for i, comment in enumerate(comments_to_process):
            with st.spinner(
                f"(1/2) Taking screenshot of comment `{comment.comment_id}`...",
            ):
                asyncio.run(take_comment_screenshot(comment, THEME))

            with st.spinner(
                f"(2/2) Generating comment `{comment.comment_id}` videocplip...",
            ):
                # Generate comment video: combine audio and image
                create_image_videoclip(
                    image_path=comment.image_path,
                    audio_path=comment.audio_path,
                    output_path=comment.video_path,
                )

            # Update progress bar
            progress = (i + 1) / len(comments_to_process)
            comments_progress_bar.progress(
                progress,
                text="Generating comments videoclips...",
            )

        with st.spinner(f"Generating outro videocplip in {post.language} language..."):
            # Generate outro clip
            outro = [
                lang["outro"]
                for lang in json.load(open("./data/languages.json"))
                if lang["lang_code"] == post.language
            ]

            tts.generate_audio_clip(
                text=outro[0],
                language=post.language,
                output_path=f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp3",
                speaker=speaker.name,
                speed=AUDIO_SPEED,
            )

            create_image_videoclip(
                image_path="./assets/others/outros/outro.png",
                audio_path=f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp3",
                output_path=f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp4",
            )

        with st.expander("Preview generated post videoclip", expanded=False):
            st.video(post.video_path)

        with st.expander("Preview generated comments videoclips", expanded=False):
            for comment in comments_to_process:
                st.video(comment.video_path)

        with st.expander("Preview generated outro videoclip", expanded=False):
            st.video(f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp4")

        if st.button("Continue to the background video selection"):
            st.session_state.continue_to_background_video = True

        reddit_videos = (
            [post.video_path]
            + [comment.video_path for comment in comments_to_process]
            + [f"./assets/others/outros/outro_{post.language}_{speaker.id}.mp4"]
        )

    except Exception as e:
        st.error(f"Error generating comments videoclips: {e}")
        st.stop()

# Only show Step 4 if Step 3 is completed
if (
    post is not None
    and st.session_state.continue_to_reddit_videos
    and st.session_state.continue_to_background_video
):
    st.header("4 - Background")

    # 4.1 - Select and download background video and audio
    st.write("Download all background media from your pool if you haven't already.")
    st.info(
        """
        You can add more media to your pool by adding them into the _background_audios.json_ and
        _background_videos.json_ files in the data folder.
        """,
        icon="ℹ️",
    )

    if st.button("Download ⬇"):
        with st.spinner("Downloading all background media files..."):
            subprocess.run(["python", "-m", "scripts.download_background_media"])

        st.success("Done!")

    st.write("Select a background video and audio.")

    background_audios = [
        MediaFile(**audio) for audio in json.load(open("./data/background_audios.json"))
    ]

    background_videos = [
        MediaFile(**video) for video in json.load(open("./data/background_videos.json"))
    ]

    # Set media select options
    background_select_options = ["Random", "Manual"]
    selected_option = st.selectbox("Choose an option", background_select_options)

    if selected_option == "Random":
        if st.button("Roll the dice! 🎲"):
            st.session_state.selected_video = random.choice(
                [video.path for video in background_videos],
            )
            st.session_state.selected_audio = random.choice(
                [audio.path for audio in background_audios],
            )

        if st.session_state.selected_video:
            st.write(f"Selected video: `{st.session_state.selected_video}`")
            with st.expander("Preview"):
                st.video(st.session_state.selected_video)

        if st.session_state.selected_audio:
            st.write(f"Selected audio: `{st.session_state.selected_audio}`")
            with st.expander("Preview"):
                st.audio(st.session_state.selected_audio)

    elif selected_option == "Manual":
        st.session_state.selected_video = st.selectbox(
            "Select a background video",
            [video.path for video in background_videos],
        )
        with st.expander("Preview"):
            st.video(st.session_state.selected_video)

        st.session_state.selected_audio = st.selectbox(
            "Select a background audio",
            [audio.path for audio in background_audios],
        )
        with st.expander("Preview"):
            st.audio(st.session_state.selected_audio)

    if st.button("Continue to the next cut and resize step"):
        st.session_state.continue_to_cut = True

# Only show Step 4.2 if Step 4.1 is completed
if (
    post is not None
    and st.session_state.continue_to_reddit_videos
    and st.session_state.continue_to_background_video
    and st.session_state.continue_to_cut
    and st.session_state.selected_video
    and st.session_state.selected_audio
):

    background_duration = sum(get_video_duration(video) for video in reddit_videos)

    try:
        with st.spinner("(1/3) Cutting and resizing the background..."):
            cut_video(
                input_path=st.session_state.selected_video,
                output_path=BACKGROUND_VIDEO_PATH.format(
                    post_id=post.post_id,
                    suffix="cutted",
                ),
                duration=background_duration,
            )

            resize_video(
                input_path=BACKGROUND_VIDEO_PATH.format(
                    post_id=post.post_id,
                    suffix="cutted",
                ),
                output_path=BACKGROUND_VIDEO_PATH.format(
                    post_id=post.post_id,
                    suffix="cutted_croped",
                ),
                height=settings.SCREEN_HEIGHT,
                width=settings.SCREEN_WIDTH,
                zoom_crop=True,
            )

        with st.spinner("(2/3) Cutting audio..."):
            # Cut the background audio
            cut_audio(
                input_path=st.session_state.selected_audio,
                output_path=BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
                duration=background_duration,
                # TODO: we need to change this to use the video duration from settings.
                fade_duration=1,
            )

        with st.spinner("(3/3) Combining video and audio..."):
            # Combine background video and audio
            combine_video_with_audio(
                video_path=BACKGROUND_VIDEO_PATH.format(
                    post_id=post.post_id,
                    suffix="cutted_croped",
                ),
                audio_path=BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
                output_path=BACKGROUND_VIDEO_PATH.format(
                    post_id=post.post_id,
                    suffix="finished",
                ),
                volume=BACKGROUND_AUDIO_VOLUME,
            )

        with st.expander("Background video"):
            st.video(
                BACKGROUND_VIDEO_PATH.format(
                    post_id=post.post_id,
                    suffix="finished",
                ),
            )

        if st.button("Continue to the combining videos step"):
            st.session_state.continue_to_video_combining = True

    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

# Only show Step 5 if all previous steps are completed
if (
    post is not None
    and st.session_state.continue_to_reddit_videos
    and st.session_state.continue_to_background_video
    and st.session_state.continue_to_cut
    and st.session_state.continue_to_video_combining
):

    st.header("5 - Create reel video")
    st.write("We will combine the background video with the reddit post videoclips.")

    with st.spinner("Combining videos..."):
        # Combine background video and audio
        combine_video_with_audio(
            video_path=BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="cutted_croped",
            ),
            audio_path=BACKGROUND_AUDIO_PATH.format(post_id=post.post_id),
            output_path=BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="finished",
            ),
            volume=BACKGROUND_AUDIO_VOLUME,
        )

        # Combine Reddit and Background videos
        overlay_videos(
            background_video=BACKGROUND_VIDEO_PATH.format(
                post_id=post.post_id,
                suffix="finished",
            ),
            overlay_videos=reddit_videos,
            output_path=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
        )

    if ADD_CAPTIONS:
        with st.spinner("Adding captions..."):
            # Add subtitles to the video
            subs_segments = stt.transcribe_audio(
                input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
                language=post.language,
            )

            # Generate SRT file
            stt.generate_srt_file(
                segments=subs_segments,
                input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
                output_directory=f"assets/posts/{post.post_id}/",
            )

            # Transform SRT to ASS format
            stt.srt_to_ass(
                input_file=f"assets/posts/{post.post_id}/reel_raw.srt",
                delete_srt=True,
            )

            # Add subtitle to video
            add_captions(
                input_file=REEL_PATH.format(post_id=post.post_id, suffix="raw"),
                output_file=REEL_PATH.format(post_id=post.post_id, suffix="subtitled"),
                subtitle_path=f"assets/posts/{post.post_id}/reel_raw.ass",
            )

    with st.spinner("Extracting video thumbnail..."):
        # Extract video thumbnail from the subtitled video
        extract_video_thumbnail(
            video_path=REEL_PATH.format(
                post_id=post.post_id,
                suffix="subtitled" if ADD_CAPTIONS else "raw",
            ),
            output_path=f"assets/posts/{post.post_id}/thumbnail.png",
        )

    st.video(
        REEL_PATH.format(
            post_id=post.post_id,
            suffix="subtitled" if ADD_CAPTIONS else "raw",
        ),
    )
