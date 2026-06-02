# MagicMirror

MagicMirror is a configurable smart mirror dashboard built with Python and PySide6. It supports live or static backgrounds, draggable overlay widgets, local desktop configuration, and a built-in web manager for remote control on your network.

## Current Feature Set

- Background modes:
  - solid color
  - camera input
  - image
  - local video
  - YouTube video
- Display controls:
  - fullscreen mode
  - mirrored video
  - 0 / 90 / 180 / 270 degree rotation
  - fill or fit scaling
  - brightness and blur controls
  - background dimming overlay
- Layout management:
  - drag widgets in edit mode
  - per-widget anchor, size, z-index, lock, and grouping
  - multiple layout pages: `default`, `morning`, `evening`, `work`, `photo-frame`
  - conditional widget visibility rules by time/day/background mode
  - grid snapping
- Configuration workflows:
  - desktop settings panel with live updates
  - web manager with live preview and remote widget editing
  - save/load profiles from `profiles/`
  - save/apply/remove templates from `templates/`
  - theme and readability presets
  - low power mode and optional auto relaunch on crash

## Included Widgets

- `time`
- `date`
- `worldclock`
- `calendar`
- `ical`
- `dailyagenda`
- `commute`
- `weatherforecast`
- `rss`
- `sports`
- `stock`
- `history`
- `countdown`
- `quotes`
- `system`
- `ip`
- `moon`
- `photomemories`
- `flightboard`
- `energyprice`
- `package`
- `sunrisesunset`
- `astronomy`

## Requirements

- Python 3.10+
- Windows is the primary tested environment in this repo
- Webcam is optional and only needed for camera background mode

## Install

Create and activate a virtual environment, then install the core dependencies:

```bash
pip install PySide6 opencv-python requests feedparser icalendar pytz certifi python-dateutil
```

Optional packages:

```bash
pip install yt-dlp psutil
```

Notes:

- `yt-dlp` is required for YouTube background playback.
- `psutil` enables the `system` widget.
- The app uses several external APIs depending on which widgets you enable.

## Run

```bash
python Main.py
```

## Basic Usage

- Open settings with the gear button.
- Enter edit mode with `E`.
- Toggle fullscreen with `F11`.
- Exit fullscreen with `Esc`.
- Open the web manager at `http://localhost:815` when web management is enabled.

## Configuration

Primary config is stored in `config.json`.

Supporting folders:

- `profiles/`: saved profile snapshots
- `templates/`: saved widget/layout templates
- `resources/`: icons and images, other related files.

Most settings can be changed from either the desktop UI or the web manager, including:

- background source and playback settings
- widget list and per-widget settings
- page assignment and visibility rules
- fonts, colors, scaling, and presets
- performance and web management options

## Widget/API Notes

- `stock` uses Financial Modeling Prep and expects `FMP_API_KEY` in the environment.
- `package` uses AfterShip and needs an API key in widget settings.
- `weatherforecast`, `sunrisesunset`, and `astronomy` rely on network lookups.
- `sports` uses ESPN public scoreboard endpoints.
- `history` uses the MuffinLabs history API.

## Web Manager

The built-in web manager provides:

- live preview
- remote widget dragging
- remote editing of general, appearance, widget, template, and profile settings
- a diagnostics view with widget refresh status

It is intended for trusted local networks. Do not expose it publicly without adding your own authentication and network protections.
