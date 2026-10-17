Markdown
# Frame Duper

<p align="center">
  <img src="assets/preview.png" alt="Frame Duper Preview" width="650"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"/>
  <img src="https://img.shields.io/badge/OS-Windows%20%7C%20Linux%20%7C%20macOS-blue?style=for-the-badge" alt="OS Support"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"/>
</p>

A sleek, modern auto-clicking utility built with Python and Tkinter. Designed with a clean flat UI, target window detection, custom hotkey toggling, and hotbar slot management.

---

## OS Compatibility

| Platform | Auto-Clicker | Target Window Selection | Standalone Executable | Notes & Requirements |
| :--- | :---: | :---: | :---: | :--- |
| **Windows (10/11)** | Yes | Yes | Yes (`.exe`) | Full support with custom title bar and native window handling. |
| **Linux (X11)** | Yes | Yes | Partial (Build on Linux) | Requires `xdotool` & `python3-tk`. Wayland support may vary. |
| **macOS** | Yes | No | Partial (Build on macOS) | Requires Accessibility permissions in System Settings. |

---

## Features

- **Left Click Automation:** Set a custom interval (in seconds) between left clicks.
- **Right Click Options:**
  - **Hold Mode:** Keeps right-click pressed continuously.
  - **Interval Mode:** Triggers right-click after each left-click with a configurable delay.
- **Hotbar Switcher:**
  - **Alternate Slots:** Automatically switches between designated slots (e.g., `1,2` or `1,3,5`).
  - **Cycle Mode:** Loops through hotbar slots 1 to 9 sequentially.
- **Target Window Focus:** Select a specific program/game window. The script automatically pauses if you switch to another window *(Windows & Linux)*.
- **Custom Start/Stop Hotkey:** Bind any key to toggle the auto-clicker (Default: `F6`).
- **Modern Interface:** Borderless window with rounded corners, pin-on-top mode, and custom title bar.

---

## Requirements & Installation

### Windows
```bash
pip install pynput pillow
Linux (Debian/Ubuntu)
Install required system tools first:

Bash
sudo apt update && sudo apt install python3-tk xdotool
pip install pynput pillow
Note: Make sure your desktop session runs on X11 for full xdotool support.

macOS
Install dependencies:

Bash
pip install pynput pillow
Note: Grant access under System Settings → Privacy & Security → Accessibility (and Input Monitoring) so pynput can capture hotkeys and trigger mouse events.

How to Run
Clone or download this repository:

Bash
git clone [https://github.com/your-username/frame-duper.git](https://github.com/your-username/frame-duper.git)
cd frame-duper
Ensure logo.png and icon.ico are placed in the project root folder.

Run the script:

Bash
python Frame_Duper.py
Building Standalone Executables
Windows (.exe)
To build a single .exe file with embedded assets:

Bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --icon="icon.ico" --add-data "logo.png;." --add-data "icon.ico;." Frame_Duper.py
The generated file will be available in the dist/ directory.

Linux / macOS
To create a native binary executable for Linux or macOS, run PyInstaller directly on the target operating system:

Bash
pyinstaller --noconfirm --onefile --windowed --add-data "logo.png:." Frame_Duper.py
