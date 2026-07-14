# DevOps Sprint Health Pro

DevOps Sprint Health Pro is a Python-based desktop application designed to provide insights into Azure DevOps sprint performance. It connects to Azure DevOps to fetch task histories, analyze work items, and generate visual graphics such as burndown charts and time registration graphs.

## Features

- **Sprint Health Graphics**: Generate detailed burndown and time-registration charts for the current or previous sprints.
- **Historical Sprint Membership**: Burndown charts use Azure DevOps Analytics snapshots when available, including member-filtered views, with WIQL `ASOF` fallback. Time-registration charts also use historical sprint membership so moved-out sprint tasks are still counted on the dates they belonged to the sprint.
- **Team Member Selection**: Filter metrics by specific team members. Syncs dynamically with DevOps.
- **Reassignments Tracking**: Analyze task reassignments over time to see who reassigned tasks, to whom, and when.
- **Built-in Image Viewer**: Explore generated graphs directly inside the app with panning and zooming support.
- **Dark Mode UI**: A sleek, modern graphical interface powered by `customtkinter`.
- **System Logs**: View real-time operation logs within the UI.

## Requirements

- Python 3.x
- Required libraries typically include:
  - `customtkinter`
  - `Pillow`
  - `matplotlib`
  - `pandas`
  - `requests`

## Setup

1. Clone or download this repository.
2. Install the required dependencies:
   ```bash
   pip install customtkinter Pillow matplotlib pandas requests
   ```
3. Run the application:
   ```bash
   python sprint_health_app.py
   ```

## Running on macOS

On macOS, avoid using Apple's bundled Command Line Tools Python (`/usr/bin/python3`) for this app. It can ship with an older Tk runtime, which may crash when `tkinter` or `customtkinter` creates the application window.

Install Python and Tk with Homebrew, then run the project inside a virtual environment:

```bash
brew install python@3.12 python-tk@3.12

/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install customtkinter Pillow matplotlib pandas requests

python sprint_health_app.py
```

If `python` is not found on macOS, use `python3` or activate the virtual environment first.

## Configuration

To use the application, you will need to provide:
- **Server URL**: Your Azure DevOps organization/server URL.
- **Area Path**: The specific area path for your team or project.
- **Sprint**: The iteration path (defaults to `@CurrentIteration`).
- **PAT Token**: A Personal Access Token (PAT) with read access to work items in Azure DevOps.

For closest parity with Azure DevOps burndown analytics, the project should have Analytics/OData enabled. If Analytics is unavailable, the app falls back to historical WIQL queries.

## Usage

1. Launch the app and enter your configuration details on the left sidebar.
2. Click **Load Combos** to populate the Area Path and Sprint lists. Click **Load Sprint Dates** to fetch dates for the selected sprint.
3. In the **Sprint Health** tab, select the type of graphic you want to generate (e.g., TimesRegistering, Burndown) and select the team members you want to include.
4. Click **GENERATE GRAPHICS**. The app will extract data from DevOps, process the history, and display the result in the built-in image viewer.
5. In the **Reassignments** tab, click **LOAD REASSIGNMENTS** to track task delegation, handoffs, and assignments history within the sprint.

## Architecture

- `sprint_health_app.py`: Main entry point for the application.
- `gui.py`: Main `customtkinter` application orchestration, threading operations, and application state logic.
- `ui/`: Reusable UI helpers, image/burndown viewers, and reassignment table rendering.
- `charts/`: Burndown and time-registration chart generation helpers.
- `devops_api.py`: Handles all HTTP API interactions with Azure DevOps.
- `config.py`: Manages saving and loading local configuration and member caches (e.g., `devops_config.json`, `members_cache.json`).
- `plotting.py`: Compatibility facade for chart generation imports.
- `reassignment.py`: Processes and analyzes task reassignment history.
- `enums.py`: Contains enumerations like `Graphic_Type`.
