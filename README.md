<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Reels Maker](#reels-maker)
  - [Examples](#examples)
  - [Setup Instructions](#setup-instructions)
  - [Run](#run)
  - [Background media:](#background-media)
  - [Makefile available commands](#makefile-available-commands)
  - [Contributing](#contributing)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Reels Maker
This repository provides the structure for automatically generating videos for social media. This repository
is under development, so it may not be fully functional.

## Examples

<details>
<summary>Video example 1</summary>

- **🔖 Reddit post**: [here](https://www.reddit.com/r/AskArgentina/comments/1j782c4/porque_me_siento_tan_mal_despu%C3%A9s_de_salir_de_joda/)

- **🎥 Link**: [here](https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_1.mp4)

- **📸 Thumbail**:

  <img src="https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_1.png" width="300">

</details>

<details>
<summary>Video example 2</summary>

- **🔖 Reddit post**: [here](https://www.reddit.com/r/AskArgentina/comments/1j6ydki/alguna_inseguridad_boluda/)

- **🎥 Link**: [here](https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_2.mp4)

- **📸 Thumbail**:

  <img src="https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_2.png" width="300">

</details>

## Setup Instructions
Follow these steps to set up the project:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/eliasprost/reddit-reels-maker.git
    cd reddit-reels-maker
    ```

2.  **Install UV:**
    Install [uv](https://github.com/astral-sh/uv) following the instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

3.  **Install Dependencies and Create Virtual Environment:**
    Use UV to install the project dependencies and create a virtual environment.
    ```bash
    uv sync
    ```

4.  **Activate the Virtual Environment:**
    Activate the virtual environment manually:
    ```bash
    source .venv/bin/activate
    ```
    Or you can set the following alias in your shell configuration file (e.g., `.bashrc`, `.zshrc`):
    ```
    alias uvenv='source .venv/bin/activate'

    # Then, you can activate the virtual environment with:
    uvenv
    ```

5.  **Install Development Dependencies:**
    Run the `make install-dev` command to install pre-commit and the unidic library, which are necessary for development.
    ```bash
    make install-dev
    ```

6.  **Obtain Reddit API Credentials:**
    Follow the instructions in [this video](https://www.youtube.com/watch?v=4Lmfgw4RZCM) to get your Reddit client ID and secret.

7.  **Configure the `.env` File:**
    Create a `.env` file in the root directory and configure it with the following variables:

    ```
    # Reddit
    REDDIT_CLIENT_ID=<your_reddit_client_id>
    REDDIT_CLIENT_SECRET=<your_reddit_client_secret>
    REDDIT_USER_NAME=<your_reddit_user_name>
    REDDIT_USER_PASSWORD=<your_reddit_user_password>

    # Video config
    SCREEN_HEIGHT=1920
    SCREEN_WIDTH=1080
    MIN_VIDEO_DURATION=70.0

    # Others
    PRESET=slow
    ```

    **Notes:**
    - Avoid using quotes for string variables.  All environment variable settings are defined in [src.config](https://github.com/eliasprost/reddit-reels-maker/blob/main/src/config.py).
    - After making changes to the `.env` file, refresh the environment variables by running `source .env` in the terminal.

## Run
run `make start` in your terminal and insert the reddit post link.
```bash
make start link={put your reddit post link here}
```
The generated contet will be saved in the `assets` folder.

## Background media:
If you want to add more background media, you can do so by adding YouTube links to the `data/background_audios.json` and `data/background_videos.json`. If you want to download all background media in one go, you can use the `download_background_media.py` by running the makefile command: `make download`.

## Makefile available commands
- Run `make install-dev` to install the project dev dependencies.
- Run `make download` to download all the background media in one go.
- Run `make start` to run the script.
- Run `make app` to start the Streamlit app.

## Contributing
Contributions are welcome!  Please submit pull requests with your proposed changes.
