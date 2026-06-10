# DevOps Sprint Health Pro

DevOps Sprint Health Pro is a Python-based desktop application designed to provide insights into Azure DevOps sprint performance. It connects to Azure DevOps to fetch task histories, analyze work items, and generate visual graphics such as burndown charts and time registration graphs.

## Features

- **Sprint Health Graphics**: Generate detailed burndown and time-registration charts for the current or previous sprints.
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

## Configuration

To use the application, you will need to provide:
- **Server URL**: Your Azure DevOps organization/server URL.
- **Area Path**: The specific area path for your team or project.
- **Sprint**: The iteration path (defaults to `@CurrentIteration`).
- **PAT Token**: A Personal Access Token (PAT) with read access to work items in Azure DevOps.

## Usage

1. Launch the app and enter your configuration details on the left sidebar.
2. Click **Load Sprint Dates** to automatically fetch the start and end dates for the selected sprint.
3. In the **Sprint Health** tab, select the type of graphic you want to generate (e.g., TimesRegistering, Burndown) and select the team members you want to include.
4. Click **GENERATE GRAPHICS**. The app will extract data from DevOps, process the history, and display the result in the built-in image viewer.
5. In the **Reassignments** tab, click **LOAD REASSIGNMENTS** to track task delegation, handoffs, and assignments history within the sprint.

## Architecture

- `sprint_health_app.py`: Main entry point for the application.
- `gui.py`: Contains the `customtkinter` UI, threading operations, and application state logic.
- `devops_api.py`: Handles all HTTP API interactions with Azure DevOps.
- `config.py`: Manages saving and loading local configuration and member caches (e.g., `devops_config.json`, `members_cache.json`).
- `plotting.py`: Generates the visual charts.
- `reassignment.py`: Processes and analyzes task reassignment history.
- `enums.py`: Contains enumerations like `Graphic_Type`.
