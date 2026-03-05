# Magic Mirror

A modular smart mirror dashboard built with Python + PySide6. It renders a configurable background (camera, image, video, YouTube, or solid color) and overlays draggable widgets for daily information.

## What It Can Do

- Multiple background modes:
  - `None` (solid color)
  - `Camera` (supports multiple camera indices)
  - `Image`
  - `Video`
  - `YouTube URL`
- Background controls:
  - mirror mode
  - 0° / 90° / 180° / 270° rotation
  - dimming overlay
  - custom background color
- Widget layout editing:
  - drag-and-drop placement in edit mode
  - per-widget anchor positioning
  - per-widget scale controls
- Desktop settings panel:
  - real-time updates
  - add/remove/rename widgets
  - font, color, refresh, fullscreen controls
- Web management UI (`:815`):
  - live preview
  - remote widget movement
  - remote settings and widget config
- Persistent configuration in `config.json`

## Included Widgets

- `time`
- `date`
- `worldclock`
- `calendar`
- `ical`
- `dailyagenda` (calendar-based)
- `commute` (calendar-based leave-time helper)
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
  - single-photo mode
  - folder rotation mode with interval
  - image scaling + folder/file picker in settings

## Requirements

- Python 3.10+
- A webcam is optional (only needed for camera mode)

## Install

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install PySide6 opencv-python requests feedparser icalendar pytz certifi
```

Optional:

```bash
pip install yt-dlp psutil
```

Notes:

- `yt-dlp` is needed for YouTube background mode.
- `psutil` is needed for the `system` widget.
- Stock widget requires an API key from Financial Modeling Prep.

## Run

```bash
python main.py
```

If your environment uses `Main.py`, run:

```bash
python Main.py
```

## Basic Usage

- Open settings: click the gear icon.
- Enter edit mode: press `E` or click the `E` button.
- Toggle fullscreen: `F11`.
- Exit fullscreen: `Esc`.
- Open web manager: `http://localhost:815`.

## Configuration

The app reads/writes `config.json` in the project root.

You can configure most options from the desktop or web UI, including:

- background mode and source
- widget list and positions
- widget-specific settings
- global appearance

## Security Note

The built-in web manager is intended for trusted/local networks. If you expose it beyond your LAN, add proper network protections.

## License

MIT (see `LICENSE.md` if present in your repo).
