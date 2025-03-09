<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Reddit Reels Maker](#reddit-reels-maker)
  - [Examples](#examples)
  - [Setup Instructions](#setup-instructions)
  - [Run](#run)
  - [Contributing](#contributing)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Reddit Reels Maker
This repository provides the structure for automatically generating videos from Reddit posts. This repository
is under development, so it may not be fully functional.

## Examples

[![Example Video 1](https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_1.png)](https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_1.mp4)

[![Example Video 2](https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_2.png)](https://raw.githubusercontent.com/eliasprost/reddit-reels-maker/main/assets/examples/example_2.mp4)

## Setup Instructions
Follow these steps to set up the project:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/eliasprost/reddit-reels-maker.git
    cd reddit-reels-maker
    ```

2.  **Install Poetry:**
    Install Poetry version 1.8 following the instructions [here](https://python-poetry.org/docs/1.8/#installation).

3.  **Install Dependencies and Create Virtual Environment:**
    Use Poetry to install the project dependencies and create a virtual environment.
    ```bash
    poetry install
    ```

4.  **Activate the Virtual Environment:**
    Activate the virtual environment using Poetry.
    ```bash
    poetry shell
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
    ```

    **Notes:**
    - Avoid using quotes for string variables.  All environment variable settings are defined in [src.config](https://github.com/eliasprost/reddit-reels-maker/blob/main/src/config.py).
    - After making changes to the `.env` file, refresh the environment variables by running `source .env` in the terminal.

## Run
run `make start` in your terminal and insert the reddit post link when is asked. The generated contet will be saved in the `assets` folder.

## Contributing
Contributions are welcome!  Please submit pull requests with your proposed changes.
