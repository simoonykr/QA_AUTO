import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, Tuple

import cv2
import numpy as np

from adb.adb_controller import AdbController, AdbError


def get_app_dir() -> Path:
    """Return the editable app directory for both Python and frozen exe runs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
CONFIG_PATH = APP_DIR / "config" / "scenarios.json"
SCREENSHOTS_DIR = APP_DIR / "screenshots"
TEMPLATES_DIR = APP_DIR / "templates"
LOGS_DIR = APP_DIR / "logs"

WINDOW_NAME = "AOS Template Tool"
TOOLBAR_HEIGHT = 192
STATUS_HEIGHT = 48
APP_PANEL_WIDTH = 370
MIN_SELECTION_SIZE = 8
BURST_COUNTS = [1, 3, 5, 10]

ACTION_MODES = [
    ("tap", "Tap"),
    ("tap_wait", "Tap + Wait"),
    ("tap_text", "Tap + Text"),
    ("tap_swipe_down", "Tap + Scroll Down"),
    ("tap_swipe_up", "Tap + Scroll Up"),
]


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def cv_font(size: str) -> tuple[float, int, int]:
    if size == "title":
        return 0.72, 2, 24
    if size == "normal":
        return 0.56, 1, 18
    if size == "button":
        return 0.50, 1, 16
    return 0.46, 1, 15


def _resolve_executable_candidate(path: Path, names: list[str]) -> Optional[Path]:
    if _is_file(path):
        return path
    if _is_dir(path):
        for name in names:
            candidate = path / name
            if _is_file(candidate):
                return candidate
    return None


def resolve_adb_path(adb_arg: str = "adb") -> str:
    """Find adb from the exe folder, common Android SDK paths, scrcpy downloads, or PATH."""
    requested = Path(adb_arg)
    names = ["adb.exe", "adb"] if requested.name.lower() == "adb" and requested.suffix == "" else [requested.name]

    requested_match = _resolve_executable_candidate(requested, names)
    if requested_match:
        return str(requested_match)

    candidates: list[Path] = []
    for name in names:
        candidates.extend([APP_DIR / name, APP_DIR / "platform-tools" / name])

    for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        env_value = os.environ.get(env_name)
        if env_value:
            for name in names:
                candidates.append(Path(env_value) / "platform-tools" / name)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for name in names:
            candidates.append(Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / name)

    downloads = Path.home() / "Downloads"
    if downloads.exists():
        for name in names:
            candidates.extend(
                [
                    downloads / "scrcpy-win64-v3.2" / "scrcpy-win64-v3.2" / name,
                    downloads / "scrcpy-win64-v3.2" / name,
                ]
            )
            candidates.extend(downloads.glob(f"scrcpy*/**/{name}"))

    for candidate in candidates:
        if _is_file(candidate):
            return str(candidate)

    path_match = shutil.which(adb_arg)
    if path_match and _is_file(Path(path_match)):
        return path_match
    return adb_arg


def safe_template_name(value: str) -> str:
    """Make a user-entered name safe for filenames and scenario/script names."""
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "template"


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def write_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError(f"Could not encode PNG: {path}")
    encoded.tofile(str(path))


class TemplateCaptureWindow:
    """OpenCV control window for app selection, scrcpy mirroring, and template capture."""

    def __init__(self) -> None:
        self.adb = AdbController(adb_path=resolve_adb_path())
        self.scrcpy_path = self._resolve_scrcpy_path()
        self.scrcpy_process: Optional[subprocess.Popen] = None
        self.scrcpy_log_file: Optional[Any] = None
        self.scrcpy_log_path: Optional[Path] = None
        self.original_image: Optional[np.ndarray] = None
        self.display_image: Optional[np.ndarray] = None
        self.screen = np.full((760, 1180, 3), 32, dtype=np.uint8)
        self.window_w = 1180
        self.window_h = 760
        self.display_scale = 1.0
        self.image_x = 0
        self.image_y = TOOLBAR_HEIGHT
        self.image_w = 0
        self.image_h = 0

        config = self._load_config()
        app_config = config.get("app", {})
        self.app_package = str(app_config.get("package", "") or "")
        self.app_activity = str(app_config.get("activity", "") or "")
        self.app_packages: list[str] = []
        self.app_index = 0
        self.app_list_scroll = 0

        self.template_name = "start_button"
        self.script_name = "default"
        self.action_mode_index = 0
        self.action_value = "1"
        self.burst_index = 2
        self.auto_register = True
        self.editing_name = False
        self.editing_script = False
        self.editing_action_value = False
        self.status = "Check device, load apps, mirror the screen, then capture a template."
        self.device_label = "Device: unchecked"

        self.dragging = False
        self.drag_start: Optional[Tuple[int, int]] = None
        self.selection_display: Optional[Tuple[int, int, int, int]] = None
        self.pending_scenario_update: Optional[Tuple[str, list[Path]]] = None
        self.show_scenarios = False
        self.show_run_monitor = False
        self.scenario_cursor = 0
        self.automation_process: Optional[subprocess.Popen] = None
        self.automation_log_lines: list[str] = []
        self.automation_status = "Idle"
        self.automation_current = "-"
        self.automation_matches = 0
        self.automation_no_matches = 0
        self.automation_return_code: Optional[int] = None
        self.automation_log_lock = threading.Lock()
        self.saving_template = False
        self.pressed_button: Optional[str] = None
        self.thumbnail_cache: dict[str, np.ndarray] = {}

        self.buttons: dict[str, Tuple[int, int, int, int]] = {}
        self.font_small = cv_font("small")
        self.font_normal = cv_font("normal")
        self.font_button = cv_font("button")
        self.font_title = cv_font("title")
        self.font_panel_title = cv_font("normal")

    def _text(
        self,
        text: str,
        pos: Tuple[int, int],
        color: Tuple[int, int, int] = (230, 230, 230),
        font: Optional[tuple[float, int, int]] = None,
    ) -> None:
        """Draw fast ASCII UI text onto the OpenCV BGR buffer."""
        scale, thickness, y_offset = font or self.font_normal
        x, y = pos
        cv2.putText(
            self.screen,
            str(text),
            (x, y + y_offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    def run(self) -> None:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, self.window_w, self.window_h)
        cv2.setMouseCallback(WINDOW_NAME, self._on_mouse)
        self.check_device()

        while True:
            if self._window_closed():
                break
            self._poll_automation_process()
            self._draw()
            cv2.imshow(WINDOW_NAME, self.screen)
            key = cv2.waitKey(30) & 0xFF
            if self._window_closed():
                break
            if key == 255:
                continue
            if not self._handle_key(key):
                break

        self.stop_mirror()
        self.stop_automation()
        cv2.destroyAllWindows()

    def _window_closed(self) -> bool:
        try:
            visible = cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE)
            return visible < 1
        except cv2.error:
            return True

    def check_device(self) -> None:
        try:
            devices = self.adb.list_device_infos()
            online = [device for device in devices if device.state == "device"]
            if not devices:
                self.device_label = "Device: none"
                self.status = "No ADB device found."
                return
            if not online:
                self.device_label = "Device: offline"
                self.status = "No online device. Allow USB debugging or reconnect USB."
                return

            serial = self.adb.ensure_device()
            selected = next((device for device in online if device.serial == serial), online[0])
            self.device_label = f"Device: {selected.label}"
            self.status = "Device connected."
        except AdbError as exc:
            self.status = f"ADB error: {exc}"

    def refresh_app_list(self) -> None:
        """Load installed user app packages from the connected device."""
        try:
            self.adb.ensure_device()
            packages = self.adb.list_user_packages()
            if not packages:
                self.status = "No user apps found."
                return
            self.app_packages = packages
            if self.app_package and self.app_package in packages:
                self.app_index = packages.index(self.app_package)
            else:
                self.app_index = 0
                self.app_package = packages[0]
                self.app_activity = ""
            self._ensure_app_visible()
            self.status = f"Apps loaded: {len(packages)}. Selected: {self.app_package}"
        except AdbError as exc:
            self.status = f"App list error: {exc}"

    def select_app(self, direction: int) -> None:
        if not self.app_packages:
            self.refresh_app_list()
            return
        self.app_index = (self.app_index + direction) % len(self.app_packages)
        self.app_package = self.app_packages[self.app_index]
        self.app_activity = ""
        self._ensure_app_visible()
        self.status = f"Selected app: {self.app_package}"

    def _ensure_app_visible(self) -> None:
        visible = self._visible_app_rows()
        if self.app_index < self.app_list_scroll:
            self.app_list_scroll = self.app_index
        elif self.app_index >= self.app_list_scroll + visible:
            self.app_list_scroll = max(0, self.app_index - visible + 1)

    def _visible_app_rows(self) -> int:
        available = max(1, self.window_h - TOOLBAR_HEIGHT - STATUS_HEIGHT - 92)
        return max(4, available // 32)

    def scroll_app_list(self, delta: int) -> None:
        if not self.app_packages:
            self.refresh_app_list()
            return
        visible = self._visible_app_rows()
        max_scroll = max(0, len(self.app_packages) - visible)
        self.app_list_scroll = max(0, min(self.app_list_scroll + delta, max_scroll))

    def save_selected_app(self) -> None:
        if not self.app_package:
            self.status = "Select an app first."
            return
        try:
            config = self._load_config()
            config["app"] = {"package": self.app_package}
            if self.app_activity:
                config["app"]["activity"] = self.app_activity
            self._write_config(config)
            self.status = f"App saved: {self.app_package}"
        except (OSError, json.JSONDecodeError) as exc:
            self.status = f"App save error: {exc}"

    def launch_selected_app(self) -> None:
        if not self.app_package:
            self.status = "Select an app to launch."
            return
        try:
            if self.app_activity:
                self.adb.start_app(self.app_package, self.app_activity)
            else:
                self.adb.start_package(self.app_package)
            self.status = f"Launched: {self.app_package}"
        except AdbError as exc:
            self.status = f"Launch error: {exc}"

    def use_foreground_app(self) -> None:
        try:
            package, activity = self.adb.get_foreground_app()
            self.app_package = package
            self.app_activity = activity
            self.save_selected_app()
            self.status = f"Current app selected: {package}"
        except AdbError as exc:
            self.status = f"Current app error: {exc}"

    def start_mirror(self) -> None:
        """Launch scrcpy for live device mirroring."""
        if self.scrcpy_process and self.scrcpy_process.poll() is None:
            self.status = "Mirror is already running."
            return
        if not self.scrcpy_path:
            self.status = "scrcpy.exe not found. Put it next to this tool or in Downloads."
            return

        try:
            serial = self.adb.ensure_device()
            self._close_scrcpy_log()
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            self.scrcpy_log_path = LOGS_DIR / f"scrcpy_{int(time.time())}.log"
            self.scrcpy_log_file = self.scrcpy_log_path.open("w", encoding="utf-8", errors="replace")
            command = [self.scrcpy_path, "-s", serial, "--no-audio", "--window-title", "AOS Mirror"]
            self.scrcpy_process = subprocess.Popen(
                command,
                cwd=str(Path(self.scrcpy_path).resolve().parent),
                stdout=self.scrcpy_log_file,
                stderr=subprocess.STDOUT,
            )
            time.sleep(0.7)
            if self.scrcpy_process.poll() is not None:
                self._close_scrcpy_log()
                self.status = f"scrcpy exited. See log: {self.scrcpy_log_path}"
                return
            self.status = "Mirror started. Click Capture when the target UI is visible."
        except (AdbError, OSError) as exc:
            self.status = f"Mirror error: {exc}"

    def stop_mirror(self) -> None:
        """Stop the scrcpy mirror process if this tool started it."""
        if self.scrcpy_process and self.scrcpy_process.poll() is None:
            self.scrcpy_process.terminate()
            try:
                self.scrcpy_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.scrcpy_process.kill()
        self.scrcpy_process = None
        self._close_scrcpy_log()

    def _close_scrcpy_log(self) -> None:
        if self.scrcpy_log_file:
            self.scrcpy_log_file.close()
        self.scrcpy_log_file = None

    def _resolve_scrcpy_path(self) -> Optional[str]:
        """Find scrcpy from the exe folder, Downloads, or PATH."""
        names = ["scrcpy.exe", "scrcpy"]
        candidates: list[Path] = []
        for name in names:
            candidates.extend([APP_DIR / name, APP_DIR / "scrcpy" / name, APP_DIR / "platform-tools" / name])

        downloads = Path.home() / "Downloads"
        if downloads.exists():
            for name in names:
                candidates.extend(
                    [
                        downloads / "scrcpy-win64-v3.2" / "scrcpy-win64-v3.2" / name,
                        downloads / "scrcpy-win64-v3.2" / name,
                    ]
                )
                candidates.extend(downloads.glob(f"scrcpy*/**/{name}"))

        for candidate in candidates:
            if _is_file(candidate):
                return str(candidate)

        for name in names:
            found = shutil.which(name)
            if found and _is_file(Path(found)):
                return found
        return None

    def refresh_screen(self) -> None:
        try:
            serial = self.adb.ensure_device()
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            path = SCREENSHOTS_DIR / f"gui_capture_{int(time.time())}.png"
            self.adb.capture_screen(path)
            self.original_image = read_image(path)
            self.selection_display = None
            self.drag_start = None
            self.device_label = f"Device: {serial}"
            self.status = f"Captured: {path.name}. Drag a region to save."
        except (AdbError, ValueError) as exc:
            self.status = f"Capture error: {exc}"

    def save_template(self) -> None:
        if self.saving_template:
            self.status = "Template save is already running."
            return
        if self.original_image is None:
            self.status = "Capture the screen first."
            return

        selection = self._display_to_original_selection()
        if not selection:
            self.status = "Drag a region first."
            return

        x1, y1, x2, y2 = selection
        if x2 - x1 < MIN_SELECTION_SIZE or y2 - y1 < MIN_SELECTION_SIZE:
            self.status = f"Selection too small. Minimum {MIN_SELECTION_SIZE}x{MIN_SELECTION_SIZE}px."
            return

        name = safe_template_name(self.template_name)
        self.template_name = name
        burst_count = BURST_COUNTS[self.burst_index]
        first_image = self.original_image.copy()

        self.saving_template = True
        self.editing_name = False
        self.status = f"Saving {burst_count} template(s)..."
        worker = threading.Thread(
            target=self._save_template_worker,
            args=(name, (x1, y1, x2, y2), burst_count, first_image, self.auto_register),
            daemon=True,
        )
        worker.start()

    def _save_template_worker(
        self,
        name: str,
        selection: Tuple[int, int, int, int],
        burst_count: int,
        first_image: np.ndarray,
        auto_register: bool,
    ) -> None:
        try:
            output_paths = self._save_template_burst(name, selection, burst_count, first_image)
            saved_label = output_paths[0].name if len(output_paths) == 1 else f"{len(output_paths)} templates"
            if auto_register:
                if self._scenario_exists(name):
                    self._register_scenario(name, output_paths, update_existing=True)
                    self.pending_scenario_update = None
                    self.status = f"Saved and updated: {saved_label}"
                else:
                    self._register_scenario(name, output_paths, update_existing=False)
                    self.status = f"Saved and registered: {saved_label}"
            else:
                self.status = f"Saved template: {saved_label}"
            self.thumbnail_cache.clear()
        except (AdbError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.status = f"Save error: {exc}"
        finally:
            self.saving_template = False

    def replace_selected_template(self) -> None:
        if self.saving_template:
            self.status = "Template save is already running."
            return
        if self.original_image is None:
            self.status = "Capture the screen first."
            return

        selected = self._selected_scenario_entry()
        if not selected:
            self.status = "Select a scenario to replace."
            return

        selection = self._display_to_original_selection()
        if not selection:
            self.status = "Drag a new region first."
            return

        x1, y1, x2, y2 = selection
        if x2 - x1 < MIN_SELECTION_SIZE or y2 - y1 < MIN_SELECTION_SIZE:
            self.status = f"Selection too small. Minimum {MIN_SELECTION_SIZE}x{MIN_SELECTION_SIZE}px."
            return

        _config, scenario_index, scenario = selected
        name = safe_template_name(str(scenario.get("name", self.template_name)))
        burst_count = BURST_COUNTS[self.burst_index]
        first_image = self.original_image.copy()

        self.saving_template = True
        self.editing_name = False
        self.template_name = name
        self.status = f"Replacing scenario template: {name}"
        worker = threading.Thread(
            target=self._replace_selected_template_worker,
            args=(scenario_index, name, (x1, y1, x2, y2), burst_count, first_image),
            daemon=True,
        )
        worker.start()

    def _replace_selected_template_worker(
        self,
        scenario_index: int,
        name: str,
        selection: Tuple[int, int, int, int],
        burst_count: int,
        first_image: np.ndarray,
    ) -> None:
        try:
            output_paths = self._save_template_burst(name, selection, burst_count, first_image)
            self._replace_scenario_template_paths(scenario_index, output_paths)
            self.thumbnail_cache.clear()
            saved_label = output_paths[0].name if len(output_paths) == 1 else f"{len(output_paths)} templates"
            self.status = f"Replaced scenario template: {name} ({saved_label})"
        except (AdbError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.status = f"Replace error: {exc}"
        finally:
            self.saving_template = False

    def _save_template_burst(
        self,
        name: str,
        selection: Tuple[int, int, int, int],
        count: int,
        first_image: np.ndarray,
    ) -> list[Path]:
        x1, y1, x2, y2 = selection
        if count <= 1:
            output_path = self._next_available_path(TEMPLATES_DIR / f"{name}.png")
            write_png(output_path, first_image[y1:y2, x1:x2])
            return [output_path]

        output_dir = self._next_available_dir(TEMPLATES_DIR / name)
        output_paths: list[Path] = []
        for index in range(1, count + 1):
            if index == 1:
                image = first_image
            else:
                self.status = f"Saving template {index}/{count}..."
                capture_path = SCREENSHOTS_DIR / f"burst_{name}_{index:03d}_{int(time.time())}.png"
                self.adb.capture_screen(capture_path)
                image = read_image(capture_path)
                time.sleep(0.12)
            if image is None:
                raise ValueError("Capture image is missing.")

            output_path = output_dir / f"{name}_{index:03d}.png"
            write_png(output_path, image[y1:y2, x1:x2])
            output_paths.append(output_path)
        return output_paths

    def _replace_scenario_template_paths(self, scenario_index: int, template_paths: list[Path]) -> None:
        config = self._load_config()
        scenarios = config.get("scenarios", [])
        if scenario_index < 0 or scenario_index >= len(scenarios):
            raise ValueError("Selected scenario no longer exists.")

        scenario = scenarios[scenario_index]
        relative_templates = [path.relative_to(APP_DIR).as_posix() for path in template_paths]
        scenario["template"] = relative_templates[0]
        if len(relative_templates) > 1:
            scenario["templates"] = relative_templates
        else:
            scenario.pop("templates", None)
        scenario.pop("match", None)
        scenario.pop("match_any", None)
        self._write_config(config)

    def _draw(self) -> None:
        self._fit_window_to_current_size()
        self.screen = np.full((self.window_h, self.window_w, 3), (245, 247, 250), dtype=np.uint8)
        self.buttons = {}
        self._draw_toolbar()
        self._draw_image()
        self._draw_script_panel()
        if self.show_scenarios:
            self._draw_scenarios_overlay()
        if self.show_run_monitor:
            self._draw_run_monitor_overlay()
        self._draw_status()

    def _fit_window_to_current_size(self) -> None:
        try:
            _x, _y, w, h = cv2.getWindowImageRect(WINDOW_NAME)
            if w > 100 and h > 100:
                self.window_w, self.window_h = w, h
        except cv2.error:
            pass

    def _app_panel_width(self) -> int:
        if self.window_w < 960:
            return 0
        return min(APP_PANEL_WIDTH, max(320, self.window_w // 3))

    def _content_width(self) -> int:
        return max(1, self.window_w - self._app_panel_width())

    def _draw_toolbar(self) -> None:
        cv2.rectangle(self.screen, (0, 0), (self.window_w, TOOLBAR_HEIGHT), (255, 255, 255), -1)
        cv2.line(self.screen, (0, TOOLBAR_HEIGHT - 1), (self.window_w, TOOLBAR_HEIGHT - 1), (214, 220, 228), 1)
        self._button("check", "Check", 10, 10, 82, 30)
        self._button("app_list", "Apps", 100, 10, 72, 30)
        self._button("launch_app", "Launch", 180, 10, 82, 30)
        self._button("foreground_app", "Current", 270, 10, 90, 30)
        self._button("mirror", "Mirror", 368, 10, 82, 30)
        self._button("stop_mirror", "Stop", 458, 10, 72, 30)
        self._button("refresh", "Capture", 538, 10, 92, 30)
        self._button("save", "Saving" if self.saving_template else "Save Tpl", 638, 10, 102, 30)
        self._button("burst", f"Burst {BURST_COUNTS[self.burst_index]}", 748, 10, 96, 30)
        self._button("replace_tpl", "Replace", 852, 10, 92, 30)

        self._button("view_scenarios", "Scripts", 700, 48, 90, 30)
        self._button("run_auto", "Stop" if self._automation_running() else "Run", 798, 48, 72, 30)
        self._button("view_monitor", "Monitor", 878, 48, 92, 30)
        self._button("prev_script", "< Script", 978, 48, 90, 30)
        self._button("next_script", "Script >", 1076, 48, 90, 30)
        self._checkbox("auto", self.auto_register, "Auto register", 720, 112)

        self._text("App:", (10, 51), (55, 65, 81), self.font_normal)
        app_text = self.app_package or "Load apps or pick current app."
        if self.app_packages:
            app_text = f"{self.app_index + 1}/{len(self.app_packages)}  {app_text}"
        self._text(app_text[:92], (82, 51), (17, 24, 39), self.font_small)

        self._text("Template:", (10, 88), (55, 65, 81), self.font_normal)
        self.buttons["name"] = (142, 86, 360, 26)
        x, y, w, h = self.buttons["name"]
        color = (230, 234, 240) if self.saving_template else (232, 240, 254) if self.editing_name else (248, 250, 252)
        cv2.rectangle(self.screen, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(self.screen, (x, y), (x + w, y + h), (148, 163, 184), 1)
        cursor = "|" if self.editing_name and int(time.time() * 2) % 2 == 0 else ""
        self._text(f"{self.template_name}{cursor}", (x + 8, y + 4), (17, 24, 39), self.font_normal)
        if self.saving_template:
            self._text("locked while saving", (x + w + 10, y + 4), (100, 116, 139), self.font_small)

        self._text("Script:", (10, 122), (55, 65, 81), self.font_normal)
        self.buttons["script"] = (142, 120, 360, 26)
        sx, sy, sw, sh = self.buttons["script"]
        script_color = (232, 240, 254) if self.editing_script else (248, 250, 252)
        cv2.rectangle(self.screen, (sx, sy), (sx + sw, sy + sh), script_color, -1)
        cv2.rectangle(self.screen, (sx, sy), (sx + sw, sy + sh), (148, 163, 184), 1)
        script_cursor = "|" if self.editing_script and int(time.time() * 2) % 2 == 0 else ""
        self._text(f"{self.script_name}{script_cursor}", (sx + 8, sy + 4), (17, 24, 39), self.font_normal)

        action_key, action_label = ACTION_MODES[self.action_mode_index]
        self._text("Action:", (10, 156), (55, 65, 81), self.font_normal)
        self._button("prev_action", "< Act", 82, 154, 70, 28)
        self._button("next_action", "Act >", 160, 154, 78, 28)
        self._text(action_label, (266, 157), (17, 24, 39), self.font_normal)
        value_label = "Value:"
        helper = "sec" if action_key == "tap_wait" else "text" if action_key == "tap_text" else "distance(px)" if action_key.startswith("tap_swipe") else "none"
        self._text(value_label, (420, 157), (55, 65, 81), self.font_normal)
        self.buttons["action_value"] = (456, 154, 170, 26)
        vx, vy, vw, vh = self.buttons["action_value"]
        value_color = (232, 240, 254) if self.editing_action_value else (248, 250, 252)
        cv2.rectangle(self.screen, (vx, vy), (vx + vw, vy + vh), value_color, -1)
        cv2.rectangle(self.screen, (vx, vy), (vx + vw, vy + vh), (148, 163, 184), 1)
        action_cursor = "|" if self.editing_action_value and int(time.time() * 2) % 2 == 0 else ""
        self._text(f"{self.action_value}{action_cursor}", (vx + 8, vy + 4), (17, 24, 39), self.font_normal)
        self._text(helper, (636, 157), (75, 85, 99), self.font_small)

        self._text(
            "Keys: C cap / S save / X run / B burst / - action",
            (760, 157),
            (75, 85, 99),
            self.font_small,
        )

    def _button(self, key: str, label: str, x: int, y: int, w: int, h: int) -> None:
        self.buttons[key] = (x, y, w, h)
        pressed = self.pressed_button == key
        fill = (188, 76, 28) if pressed else (235, 99, 37)
        border = (124, 45, 18) if pressed else (216, 78, 29)
        offset = 2 if pressed else 0
        if not pressed:
            cv2.rectangle(self.screen, (x + 2, y + 2), (x + w + 2, y + h + 2), (190, 198, 210), -1)
        cv2.rectangle(self.screen, (x + offset, y + offset), (x + w + offset, y + h + offset), fill, -1)
        cv2.rectangle(self.screen, (x + offset, y + offset), (x + w + offset, y + h + offset), border, 1)
        if pressed:
            cv2.line(self.screen, (x + offset + 2, y + offset + 2), (x + w + offset - 2, y + offset + 2), (102, 37, 15), 1)
        self._text(label, (x + 8 + offset, y + 6 + offset), (255, 255, 255), self.font_button)

    def _checkbox(self, key: str, checked: bool, label: str, x: int, y: int) -> None:
        self.buttons[key] = (x, y - 13, 230, 24)
        cv2.rectangle(self.screen, (x, y - 12), (x + 18, y + 6), (255, 255, 255), -1)
        cv2.rectangle(self.screen, (x, y - 12), (x + 18, y + 6), (100, 116, 139), 1)
        if checked:
            cv2.line(self.screen, (x + 4, y - 3), (x + 8, y + 2), (235, 99, 37), 2)
            cv2.line(self.screen, (x + 8, y + 2), (x + 15, y - 9), (235, 99, 37), 2)
        self._text(label, (x + 26, y - 12), (55, 65, 81), self.font_small)

    def _draw_image(self) -> None:
        if self.original_image is None:
            self._text(
                "No capture yet. Watch mirror, then click Capture.",
                (30, TOOLBAR_HEIGHT + 42),
                (30, 41, 59),
                self.font_title,
            )
            return

        available_w = self._content_width()
        available_h = max(1, self.window_h - TOOLBAR_HEIGHT - STATUS_HEIGHT)
        original_h, original_w = self.original_image.shape[:2]
        self.display_scale = min(available_w / original_w, available_h / original_h, 1.0)
        self.image_w = max(1, int(original_w * self.display_scale))
        self.image_h = max(1, int(original_h * self.display_scale))
        self.image_x = int((available_w - self.image_w) / 2)
        self.image_y = TOOLBAR_HEIGHT
        self.display_image = cv2.resize(self.original_image, (self.image_w, self.image_h), interpolation=cv2.INTER_AREA)

        self.screen[self.image_y : self.image_y + self.image_h, self.image_x : self.image_x + self.image_w] = self.display_image
        cv2.rectangle(
            self.screen,
            (self.image_x, self.image_y),
            (self.image_x + self.image_w, self.image_y + self.image_h),
            (148, 163, 184),
            1,
        )

        if self.selection_display:
            x1, y1, x2, y2 = self.selection_display
            cv2.rectangle(self.screen, (x1, y1), (x2, y2), (0, 229, 255), 2)

    def _draw_app_panel(self) -> None:
        panel_w = self._app_panel_width()
        if panel_w <= 0:
            return

        x = self.window_w - panel_w
        y = TOOLBAR_HEIGHT
        bottom = self.window_h - STATUS_HEIGHT
        cv2.rectangle(self.screen, (x, y), (self.window_w, bottom), (255, 255, 255), -1)
        cv2.line(self.screen, (x, y), (x, bottom), (214, 220, 228), 1)

        self._text("Apps", (x + 18, y + 16), (15, 23, 42), self.font_panel_title)
        if self.app_packages:
            summary = f"{len(self.app_packages)} apps / selected {self.app_index + 1}"
        else:
            summary = "Click Apps to load packages."
        self._text(summary, (x + 18, y + 45), (71, 85, 105), self.font_small)

        self._button("app_page_up", "Up", x + 18, y + 72, 72, 28)
        self._button("app_page_down", "Down", x + 98, y + 72, 82, 28)
        self._button("app_select_save", "Save", x + 188, y + 72, 104, 28)

        list_y = y + 112
        row_h = 32
        visible = self._visible_app_rows()
        end = min(len(self.app_packages), self.app_list_scroll + visible)
        if not self.app_packages:
            self._text(
                "No apps loaded yet.",
                (x + 18, list_y + 8),
                (71, 85, 105),
                self.font_normal,
            )
            self._text(
                "Click Apps or press L.",
                (x + 18, list_y + 36),
                (100, 116, 139),
                self.font_small,
            )
            return

        for visible_index, package_index in enumerate(range(self.app_list_scroll, end)):
            row_y = list_y + visible_index * row_h
            package = self.app_packages[package_index]
            is_selected = package_index == self.app_index
            is_pressed = self.pressed_button == f"app_row_{package_index}"
            fill = (255, 213, 181) if is_pressed else (254, 234, 219) if is_selected else (248, 250, 252)
            border = (188, 76, 28) if is_pressed else (235, 99, 37) if is_selected else (226, 232, 240)
            cv2.rectangle(self.screen, (x + 14, row_y), (self.window_w - 14, row_y + row_h - 4), fill, -1)
            cv2.rectangle(self.screen, (x + 14, row_y), (self.window_w - 14, row_y + row_h - 4), border, 1)
            self.buttons[f"app_row_{package_index}"] = (x + 14, row_y, panel_w - 28, row_h - 4)
            text_color = (30, 64, 175) if is_selected else (15, 23, 42)
            self._text(package[:42], (x + 24, row_y + 5), text_color, self.font_small)

        if end < len(self.app_packages):
            self._text("More apps below.", (x + 18, bottom - 26), (100, 116, 139), self.font_small)

    def _draw_script_panel(self) -> None:
        panel_w = self._app_panel_width()
        if panel_w <= 0:
            return

        x = self.window_w - panel_w
        y = TOOLBAR_HEIGHT
        bottom = self.window_h - STATUS_HEIGHT
        cv2.rectangle(self.screen, (x, y), (self.window_w, bottom), (255, 255, 255), -1)
        cv2.line(self.screen, (x, y), (x, bottom), (214, 220, 228), 1)

        try:
            config = self._load_config()
            scenarios = config.get("scenarios", [])
            entries = self._visible_scenario_entries(scenarios)
            self._clamp_scenario_cursor(len(entries))
        except (OSError, json.JSONDecodeError) as exc:
            self._text("Script", (x + 18, y + 16), (15, 23, 42), self.font_panel_title)
            self._text(f"Could not read scenarios.json: {exc}"[:42], (x + 18, y + 48), (185, 28, 28), self.font_small)
            return

        self._text("Script", (x + 18, y + 16), (15, 23, 42), self.font_panel_title)
        self._text(f"{self.script_name} / {len(entries)} scenarios"[:42], (x + 18, y + 45), (71, 85, 105), self.font_small)
        self._text("Saved templates linked to this script.", (x + 18, y + 70), (100, 116, 139), self.font_small)

        row_y = y + 102
        row_h = 86
        thumb_w = 76
        thumb_h = 62
        visible_rows = max(1, (bottom - row_y - 12) // row_h)
        if not entries:
            self._text("No scenario yet.", (x + 18, row_y + 4), (71, 85, 105), self.font_normal)
            self._text("Capture a template and click Save Tpl.", (x + 18, row_y + 34), (100, 116, 139), self.font_small)
            return

        start = max(0, min(self.scenario_cursor - visible_rows + 1, len(entries) - visible_rows))
        visible_entries = entries[start : start + visible_rows]
        for visible_index, (scenario_index, scenario) in enumerate(visible_entries):
            current_y = row_y + visible_index * row_h
            is_selected = start + visible_index == self.scenario_cursor
            is_pressed = self.pressed_button == f"scenario_row_{scenario_index}"
            fill = (254, 234, 219) if is_pressed else (255, 246, 239) if is_selected else (248, 250, 252)
            border = (235, 99, 37) if is_selected or is_pressed else (226, 232, 240)
            cv2.rectangle(self.screen, (x + 14, current_y), (self.window_w - 14, current_y + row_h - 8), fill, -1)
            cv2.rectangle(self.screen, (x + 14, current_y), (self.window_w - 14, current_y + row_h - 8), border, 1)
            if is_selected:
                cv2.rectangle(self.screen, (x + 14, current_y), (x + 18, current_y + row_h - 8), (235, 99, 37), -1)
            self.buttons[f"scenario_row_{scenario_index}"] = (x + 14, current_y, panel_w - 28, row_h - 8)

            thumb_x = x + 24
            thumb_y = current_y + 10
            cv2.rectangle(self.screen, (thumb_x, thumb_y), (thumb_x + thumb_w, thumb_y + thumb_h), (241, 245, 249), -1)
            cv2.rectangle(self.screen, (thumb_x, thumb_y), (thumb_x + thumb_w, thumb_y + thumb_h), (203, 213, 225), 1)
            thumb = self._scenario_thumbnail(scenario, thumb_w - 4, thumb_h - 4)
            if thumb is not None:
                th, tw = thumb.shape[:2]
                tx = thumb_x + 2 + (thumb_w - 4 - tw) // 2
                ty = thumb_y + 2 + (thumb_h - 4 - th) // 2
                self.screen[ty : ty + th, tx : tx + tw] = thumb
            else:
                self._text("No img", (thumb_x + 9, thumb_y + 18), (100, 116, 139), self.font_small)

            action = scenario.get("action", {}).get("type", "")
            template_count = len(self._scenario_template_paths(scenario))
            name = str(scenario.get("name", ""))
            self._text(f"{start + visible_index + 1}. {name}"[:28], (x + 112, current_y + 5), (15, 23, 42), self.font_small)
            self._text(f"{template_count} img / {action}"[:30], (x + 112, current_y + 31), (71, 85, 105), self.font_small)
            self._text(str(scenario.get("threshold", 0.85))[:8], (x + 112, current_y + 55), (100, 116, 139), self.font_small)

        if len(entries) > visible_rows:
            self._text("Wheel or Up/Down to move.", (x + 18, bottom - 26), (100, 116, 139), self.font_small)

    def _draw_run_monitor(self, x: int, y: int, panel_w: int, bottom: int) -> None:
        cv2.line(self.screen, (x + 14, y - 8), (self.window_w - 14, y - 8), (226, 232, 240), 1)
        self._text("Run Monitor", (x + 18, y), (15, 23, 42), self.font_panel_title)
        state_color = (22, 101, 52) if self._automation_running() else (71, 85, 105)
        self._text(self.automation_status[:34], (x + 18, y + 28), state_color, self.font_small)
        self._text(f"Step: {self.automation_current}"[:39], (x + 18, y + 52), (30, 41, 59), self.font_small)
        self._text(
            f"Matched {self.automation_matches} / No match {self.automation_no_matches}",
            (x + 18, y + 76),
            (71, 85, 105),
            self.font_small,
        )

        with self.automation_log_lock:
            lines = list(self.automation_log_lines[-4:])
        log_y = y + 106
        if not lines:
            self._text("Press Run to start automation.", (x + 18, log_y), (100, 116, 139), self.font_small)
            return
        for line in lines:
            clean = self._compact_log_line(line)
            self._text(clean[:42], (x + 18, log_y), (71, 85, 105), self.font_small)
            log_y += 22
            if log_y > bottom - 22:
                break

    def _compact_log_line(self, line: str) -> str:
        if "Matched scenario=" in line:
            return line.split("Matched ", 1)[-1]
        if "No scenario matched" in line:
            return "No scenario matched."
        for marker in ("Selected script:", "Starting run", "Run mode:", "Report written:", "Automation finished."):
            if marker in line:
                return line.split(marker, 1)[-1].strip() if marker.endswith(":") else line.split("main:", 1)[-1].strip()
        return line.split("main:", 1)[-1].strip() if "main:" in line else line.strip()

    def _draw_run_monitor_overlay(self) -> None:
        width = min(self.window_w - 52, 940)
        height = min(self.window_h - TOOLBAR_HEIGHT - 72, 600)
        x = max(20, (self.window_w - width) // 2)
        y = TOOLBAR_HEIGHT + 24
        cv2.rectangle(self.screen, (x, y), (x + width, y + height), (255, 255, 255), -1)
        cv2.rectangle(self.screen, (x, y), (x + width, y + height), (235, 99, 37), 2)

        self._text("Run Monitor", (x + 18, y + 14), (15, 23, 42), self.font_panel_title)
        self._button("monitor_close", "Close", x + width - 94, y + 14, 72, 28)
        self._button("monitor_run", "Stop" if self._automation_running() else "Run", x + width - 174, y + 14, 72, 28)

        state_color = (22, 101, 52) if self._automation_running() else (71, 85, 105)
        self._text(f"Script: {self.script_name}"[:80], (x + 18, y + 58), (30, 41, 59), self.font_normal)
        self._text(f"Status: {self.automation_status}"[:80], (x + 18, y + 88), state_color, self.font_normal)
        self._text(f"Step: {self.automation_current}"[:95], (x + 18, y + 118), (30, 41, 59), self.font_normal)
        self._text(
            f"Matched: {self.automation_matches}    No match: {self.automation_no_matches}",
            (x + 18, y + 148),
            (71, 85, 105),
            self.font_normal,
        )

        cv2.line(self.screen, (x + 18, y + 188), (x + width - 18, y + 188), (226, 232, 240), 1)
        self._text("Recent Log", (x + 18, y + 202), (15, 23, 42), self.font_normal)
        with self.automation_log_lock:
            lines = list(self.automation_log_lines[-16:])
        if not lines:
            self._text("Press Run to start automation.", (x + 18, y + 238), (100, 116, 139), self.font_small)
            return

        log_y = y + 238
        for line in lines:
            clean = self._compact_log_line(line)
            text_color = (22, 101, 52) if "scenario='" in clean else (185, 28, 28) if "No scenario" in clean else (71, 85, 105)
            self._text(clean[:110], (x + 18, log_y), text_color, self.font_small)
            log_y += 24
            if log_y > y + height - 30:
                break

    def _scenario_template_paths(self, scenario: dict[str, Any]) -> list[Path]:
        raw_paths = scenario.get("templates")
        if isinstance(raw_paths, list) and raw_paths:
            paths = [str(path) for path in raw_paths]
        else:
            template = scenario.get("template")
            paths = [str(template)] if template else []
        result: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            result.append(path if path.is_absolute() else APP_DIR / path)
        return result

    def _scenario_thumbnail(self, scenario: dict[str, Any], max_w: int, max_h: int) -> Optional[np.ndarray]:
        paths = self._scenario_template_paths(scenario)
        if not paths:
            return None
        path = paths[0]
        try:
            stat = path.stat()
            cache_key = f"{path}|{stat.st_mtime_ns}|{max_w}x{max_h}"
        except OSError:
            return None
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            image = read_image(path)
        except (OSError, ValueError):
            return None
        h, w = image.shape[:2]
        scale = min(max_w / max(1, w), max_h / max(1, h), 1.0)
        resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        if len(self.thumbnail_cache) > 200:
            self.thumbnail_cache.clear()
        self.thumbnail_cache[cache_key] = resized
        return resized

    def _draw_scenarios_overlay(self) -> None:
        x = 26
        y = TOOLBAR_HEIGHT + 24
        width = min(self.window_w - 52, 980)
        height = min(self.window_h - TOOLBAR_HEIGHT - 72, 560)
        cv2.rectangle(self.screen, (x, y), (x + width, y + height), (255, 255, 255), -1)
        cv2.rectangle(self.screen, (x, y), (x + width, y + height), (235, 99, 37), 2)
        self._text(
            "scenarios.json (V close, O open, X run, Up/Down select)",
            (x + 16, y + 12),
            (15, 23, 42),
            self.font_normal,
        )
        button_y = y + 42
        button_x = x + width - 508
        self._button("scenario_open", "Open", button_x, button_y, 64, 28)
        self._button("scenario_load", "Load", button_x + 70, button_y, 64, 28)
        self._button("scenario_insert_before", "Before", button_x + 140, button_y, 76, 28)
        self._button("scenario_insert_after", "After", button_x + 222, button_y, 66, 28)
        self._button("scenario_apply", "Apply", button_x + 294, button_y, 70, 28)
        self._button("scenario_delete", "Delete", button_x + 370, button_y, 72, 28)

        try:
            config = self._load_config()
            scenarios = config.get("scenarios", [])
            script_counts = self._script_counts(scenarios)
            visible_entries = self._visible_scenario_entries(scenarios)
            self._clamp_scenario_cursor(len(visible_entries))
            lines = [
                f"App: {config.get('app', {}).get('package', '')}/{config.get('app', {}).get('activity', '')}",
                f"Loop: interval={config.get('loop', {}).get('interval_seconds', '')}, max={config.get('loop', {}).get('max_iterations', '')}",
                f"Script: {self.script_name} ({script_counts.get(self.script_name, 0)} scenarios)",
                f"Scripts: {', '.join(f'{name}({count})' for name, count in script_counts.items()) or 'none'}",
                "Edit: Load edits row. Before/After inserts form. Keys: I before, F after, E apply.",
            ]
            line_y = y + 92
            for line in lines:
                self._text(line[:130], (x + 18, line_y - 16), (30, 41, 59), self.font_small)
                line_y += 25

            for index, (scenario_index, scenario) in enumerate(visible_entries[:12], start=1):
                action = scenario.get("action", {}).get("type", "")
                template_label = scenario.get("template", "")
                templates_value = scenario.get("templates")
                if isinstance(templates_value, list) and len(templates_value) > 1:
                    template_label = f"{len(templates_value)} templates"
                row_y = line_y - 2
                is_selected = index - 1 == self.scenario_cursor
                is_pressed = self.pressed_button == f"scenario_row_{scenario_index}"
                fill = (254, 234, 219) if is_pressed else (255, 246, 239) if is_selected else (255, 255, 255)
                border = (235, 99, 37) if is_selected or is_pressed else (226, 232, 240)
                cv2.rectangle(self.screen, (x + 12, row_y), (x + width - 12, row_y + 27), fill, -1)
                if is_selected or is_pressed:
                    cv2.rectangle(self.screen, (x + 12, row_y), (x + width - 12, row_y + 27), border, 1)
                    cv2.rectangle(self.screen, (x + 12, row_y), (x + 16, row_y + 27), (235, 99, 37), -1)
                self.buttons[f"scenario_row_{scenario_index}"] = (x + 12, row_y, width - 24, 27)
                line = (
                    f"{index}. {scenario.get('name', '')} | {template_label} | "
                    f"threshold={scenario.get('threshold', '')} | action={action}"
                )
                self._text(line[:130], (x + 22, row_y + 1), (30, 41, 59), self.font_small)
                line_y += 30

            if len(visible_entries) > 12:
                self._text(f"... {len(visible_entries) - 12} more. Press O for full JSON.", (x + 18, line_y - 16), (100, 116, 139), self.font_small)
        except (OSError, json.JSONDecodeError) as exc:
            self._text(f"Could not read scenarios.json: {exc}", (x + 18, y + 64), (30, 41, 59), self.font_small)

    def _draw_status(self) -> None:
        y = self.window_h - 26
        cv2.rectangle(self.screen, (0, self.window_h - STATUS_HEIGHT), (self.window_w, self.window_h), (255, 255, 255), -1)
        cv2.line(self.screen, (0, self.window_h - STATUS_HEIGHT), (self.window_w, self.window_h - STATUS_HEIGHT), (214, 220, 228), 1)
        self._text(self.device_label[:90], (10, y - 31), (71, 85, 105), self.font_small)
        self._text(self.status[:135], (10, y - 11), (15, 23, 42), self.font_small)

    def _on_mouse(self, event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            button_key = self._button_at(x, y)
            if button_key:
                self.pressed_button = button_key
                return
            self._clear_editing_if_plain_click()
            if not self._point_in_image(x, y):
                return
            self.dragging = True
            self.drag_start = self._clamp_to_image(x, y)
            self.selection_display = (*self.drag_start, *self.drag_start)
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging and self.drag_start:
            cx, cy = self._clamp_to_image(x, y)
            self.selection_display = (*self.drag_start, cx, cy)
        elif event == cv2.EVENT_LBUTTONUP and self.dragging and self.drag_start:
            cx, cy = self._clamp_to_image(x, y)
            self.selection_display = (*self.drag_start, cx, cy)
            self.dragging = False
            selection = self._display_to_original_selection()
            if selection:
                ox1, oy1, ox2, oy2 = selection
                self.status = f"Selected region: x={ox1}, y={oy1}, w={ox2 - ox1}, h={oy2 - oy1}"
        elif event == cv2.EVENT_LBUTTONUP and self.pressed_button:
            pressed_key = self.pressed_button
            self.pressed_button = None
            if self._point_in_button(pressed_key, x, y):
                self._activate_button(pressed_key)
        elif event == cv2.EVENT_MOUSEWHEEL:
            if x >= self._content_width():
                direction = -1 if _flags > 0 else 1
                self.select_scenario(direction)

    def _button_at(self, x: int, y: int) -> Optional[str]:
        for key, rect in self.buttons.items():
            rx, ry, rw, rh = rect
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return key
        return None

    def _point_in_button(self, key: str, x: int, y: int) -> bool:
        rect = self.buttons.get(key)
        if not rect:
            return False
        rx, ry, rw, rh = rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def _activate_button(self, key: str) -> bool:
        if key.startswith("app_row_"):
            self.app_index = int(key.rsplit("_", 1)[1])
            self.app_package = self.app_packages[self.app_index]
            self.app_activity = ""
            self._ensure_app_visible()
            self.status = f"Selected app: {self.app_package}"
        elif key.startswith("scenario_row_"):
            self.select_scenario_by_config_index(int(key.rsplit("_", 2)[2]))
        elif key == "app_page_up":
            self.scroll_app_list(-self._visible_app_rows())
        elif key == "app_page_down":
            self.scroll_app_list(self._visible_app_rows())
        elif key == "app_select_save":
            self.save_selected_app()
        elif key == "check":
            self.check_device()
        elif key == "app_list":
            self.refresh_app_list()
        elif key == "prev_app":
            self.select_app(-1)
        elif key == "next_app":
            self.select_app(1)
        elif key == "save_app":
            self.save_selected_app()
        elif key == "launch_app":
            self.launch_selected_app()
        elif key == "foreground_app":
            self.use_foreground_app()
        elif key == "mirror":
            self.start_mirror()
        elif key == "stop_mirror":
            self.stop_mirror()
            self.status = "Mirror stopped."
        elif key == "refresh":
            self.refresh_screen()
        elif key == "save":
            self.save_template()
        elif key == "replace_tpl":
            self.replace_selected_template()
        elif key == "burst":
            self.select_burst_count()
        elif key == "view_scenarios":
            self.show_scenarios = not self.show_scenarios
            self.status = "Showing scenarios." if self.show_scenarios else "Closed scenario view."
        elif key == "view_monitor":
            self.show_run_monitor = not self.show_run_monitor
            self.status = "Showing run monitor." if self.show_run_monitor else "Closed run monitor."
        elif key == "monitor_close":
            self.show_run_monitor = False
            self.status = "Closed run monitor."
        elif key == "monitor_run":
            self.run_automation()
        elif key == "scenario_open":
            self.open_scenarios_file()
        elif key == "scenario_load":
            self.load_selected_scenario_to_form()
        elif key == "scenario_insert_before":
            self.insert_form_near_selected_scenario(before=True)
        elif key == "scenario_insert_after":
            self.insert_form_near_selected_scenario(before=False)
        elif key == "scenario_apply":
            self.apply_form_to_selected_scenario()
        elif key == "scenario_delete":
            self.delete_selected_scenario()
        elif key == "run_auto":
            self.run_automation()
        elif key == "prev_script":
            self.select_script(-1)
        elif key == "next_script":
            self.select_script(1)
        elif key == "prev_action":
            self.select_action(-1)
        elif key == "next_action":
            self.select_action(1)
        elif key == "auto":
            self.auto_register = not self.auto_register
        elif key == "name":
            if self.saving_template:
                self.status = "Template name is locked while saving."
                return True
            self.editing_name = True
            self.editing_script = False
            self.editing_action_value = False
            self.status = "Editing template. Press Enter."
        elif key == "script":
            self.editing_script = True
            self.editing_name = False
            self.editing_action_value = False
            self.status = "Editing script. Press Enter."
        elif key == "action_value":
            self.editing_action_value = True
            self.editing_name = False
            self.editing_script = False
            self.status = "Editing action value. Press Enter."
        else:
            return False
        return True

    def _clear_editing_if_plain_click(self) -> None:
        self.editing_name = False
        self.editing_script = False
        self.editing_action_value = False

    def _handle_key(self, key: int) -> bool:
        if self.pending_scenario_update:
            if key in (ord("y"), ord("Y")):
                name, path = self.pending_scenario_update
                self._register_scenario(name, path, update_existing=True)
                self.pending_scenario_update = None
                self.status = f"Scenario updated: {name}"
                return True
            if key in (ord("n"), ord("N")):
                self.pending_scenario_update = None
                self.status = "Skipped scenario update."
                return True

        if self.editing_name:
            if self.saving_template:
                self.editing_name = False
                self.status = "Template name is locked while saving."
                return True
            if key in (13, 10):
                self.template_name = safe_template_name(self.template_name)
                self.editing_name = False
                self.status = f"Template set: {self.template_name}"
            elif key in (8, 127):
                self.template_name = self.template_name[:-1]
            elif key == 27:
                self.editing_name = False
            elif 32 <= key <= 126 and len(self.template_name) < 80:
                self.template_name += chr(key)
            return True

        if self.editing_script:
            if key in (13, 10):
                self.script_name = safe_template_name(self.script_name)
                self.editing_script = False
                self.status = f"Script set: {self.script_name}"
            elif key in (8, 127):
                self.script_name = self.script_name[:-1]
            elif key == 27:
                self.editing_script = False
            elif 32 <= key <= 126 and len(self.script_name) < 80:
                self.script_name += chr(key)
            return True

        if self.editing_action_value:
            if key in (13, 10):
                self.editing_action_value = False
                self.status = f"Action value set: {self.action_value}"
            elif key in (8, 127):
                self.action_value = self.action_value[:-1]
            elif key == 27:
                self.editing_action_value = False
            elif 32 <= key <= 126 and len(self.action_value) < 120:
                self.action_value += chr(key)
            return True

        if self.show_scenarios:
            if key in (ord("j"), ord("J")):
                self.select_scenario(1)
                return True
            if key in (ord("k"), ord("K")):
                self.select_scenario(-1)
                return True
            if key in (13, 10):
                self.load_selected_scenario_to_form()
                return True
            if key in (ord("i"), ord("I")):
                self.insert_form_near_selected_scenario(before=True)
                return True
            if key in (ord("f"), ord("F")):
                self.insert_form_near_selected_scenario(before=False)
                return True
            if key in (ord("e"), ord("E")):
                self.apply_form_to_selected_scenario()
                return True
            if key in (8, 127):
                self.delete_selected_scenario()
                return True

        if self.show_run_monitor:
            if key in (ord("v"), ord("V"), 27):
                self.show_run_monitor = False
                self.status = "Closed run monitor."
                return True
            if key in (ord("x"), ord("X")):
                self.run_automation()
                return True

        if key in (ord("q"), ord("Q"), 27):
            return False
        if key in (ord("d"), ord("D")):
            self.check_device()
        elif key in (ord("m"), ord("M")):
            self.start_mirror()
        elif key in (ord("c"), ord("C"), ord("r"), ord("R")):
            self.refresh_screen()
        elif key in (ord("s"), ord("S")):
            self.save_template()
        elif key in (ord("v"), ord("V")):
            self.show_scenarios = not self.show_scenarios
            self.status = "Showing scenarios." if self.show_scenarios else "Closed scenario view."
        elif key in (ord("g"), ord("G")):
            self.show_run_monitor = not self.show_run_monitor
            self.status = "Showing run monitor." if self.show_run_monitor else "Closed run monitor."
        elif key in (ord("o"), ord("O")):
            self.open_scenarios_file()
        elif key in (ord("x"), ord("X")):
            self.run_automation()
        elif key == ord("["):
            self.select_script(-1)
        elif key == ord("]"):
            self.select_script(1)
        elif key == ord("-"):
            self.select_action(-1)
        elif key == ord("="):
            self.select_action(1)
        elif key == ord(","):
            self.select_app(-1)
        elif key == ord("."):
            self.select_app(1)
        elif key in (ord("l"), ord("L")):
            self.refresh_app_list()
        elif key in (ord("u"), ord("U")):
            self.use_foreground_app()
        elif key in (ord("a"), ord("A")):
            self.auto_register = not self.auto_register
        elif key in (ord("b"), ord("B")):
            self.select_burst_count()
        elif key in (ord("n"), ord("N")):
            if self.saving_template:
                self.status = "Template name is locked while saving."
            else:
                self.editing_name = True
        elif key in (ord("p"), ord("P")):
            self.editing_script = True
        return True

    def _point_in_image(self, x: int, y: int) -> bool:
        return self.image_x <= x <= self.image_x + self.image_w and self.image_y <= y <= self.image_y + self.image_h

    def _clamp_to_image(self, x: int, y: int) -> Tuple[int, int]:
        return (
            max(self.image_x, min(x, self.image_x + self.image_w)),
            max(self.image_y, min(y, self.image_y + self.image_h)),
        )

    def _display_to_original_selection(self) -> Optional[Tuple[int, int, int, int]]:
        if self.original_image is None or not self.selection_display or self.display_scale <= 0:
            return None

        x1, y1, x2, y2 = self.selection_display
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        original_h, original_w = self.original_image.shape[:2]

        ox1 = max(0, min(int(round((left - self.image_x) / self.display_scale)), original_w))
        ox2 = max(0, min(int(round((right - self.image_x) / self.display_scale)), original_w))
        oy1 = max(0, min(int(round((top - self.image_y) / self.display_scale)), original_h))
        oy2 = max(0, min(int(round((bottom - self.image_y) / self.display_scale)), original_h))

        if ox2 <= ox1 or oy2 <= oy1:
            return None
        return ox1, oy1, ox2, oy2

    def _next_available_path(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return path
        for index in range(1, 1000):
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise ValueError("Could not find an available numbered filename.")

    def _next_available_dir(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.mkdir(parents=True)
            return path
        for index in range(1, 1000):
            candidate = path.with_name(f"{path.name}_{index}")
            if not candidate.exists():
                candidate.mkdir(parents=True)
                return candidate
        raise ValueError("Could not find an available numbered directory.")

    def _scenario_exists(self, name: str) -> bool:
        config = self._load_config()
        return any(scenario.get("name") == name for scenario in config.get("scenarios", []))

    def _register_scenario(self, name: str, template_paths: list[Path], update_existing: bool) -> None:
        config = self._load_config()
        scenarios = config.setdefault("scenarios", [])
        scenario = self._scenario_from_template_paths(name, template_paths)

        for index, existing in enumerate(scenarios):
            if existing.get("name") == name:
                if update_existing:
                    merged = {**existing, **scenario}
                    if len(scenario.get("templates", [])) <= 1:
                        merged.pop("templates", None)
                    scenarios[index] = merged
                    self._write_config(config)
                return

        scenarios.append(scenario)
        self._write_config(config)

    def _scenario_from_template_paths(self, name: str, template_paths: list[Path]) -> dict[str, Any]:
        relative_templates = [path.relative_to(APP_DIR).as_posix() for path in template_paths]
        scenario: dict[str, Any] = {
            "name": name,
            "script": safe_template_name(self.script_name),
            "template": relative_templates[0],
            "threshold": 0.85,
            "action": self._build_selected_action(),
        }
        if len(relative_templates) > 1:
            scenario["templates"] = relative_templates
        return scenario

    def _find_saved_template_paths(self, name: str) -> list[Path]:
        safe_name = safe_template_name(name)
        direct_path = TEMPLATES_DIR / f"{safe_name}.png"
        if direct_path.exists():
            return [direct_path]

        directory = TEMPLATES_DIR / safe_name
        if directory.exists():
            paths = sorted(path for path in directory.glob("*.png") if path.is_file())
            if paths:
                return paths

        matching_dirs = sorted(path for path in TEMPLATES_DIR.glob(f"{safe_name}_*") if path.is_dir())
        for directory in matching_dirs:
            paths = sorted(path for path in directory.glob("*.png") if path.is_file())
            if paths:
                return paths
        return []

    def _build_form_scenario_for_insert(self) -> Optional[dict[str, Any]]:
        name = safe_template_name(self.template_name)
        template_paths = self._find_saved_template_paths(name)
        if not template_paths:
            self.status = f"Save template first: {name}"
            return None
        return self._scenario_from_template_paths(name, template_paths)

    def _build_selected_action(self) -> dict[str, Any]:
        mode = ACTION_MODES[self.action_mode_index][0]
        if mode == "tap":
            return {"type": "tap"}
        if mode == "tap_wait":
            return {"type": "tap_wait", "seconds": self._float_action_value(default=1.0)}
        if mode == "tap_text":
            return {"type": "tap_text", "text": self.action_value, "delay_before_text": 0.3}
        if mode == "tap_swipe_up":
            return {
                "type": "tap_swipe",
                "direction": "up",
                "distance": int(self._float_action_value(default=900)),
                "duration_ms": 500,
                "delay_seconds": 0.2,
            }
        if mode == "tap_swipe_down":
            return {
                "type": "tap_swipe",
                "direction": "down",
                "distance": int(self._float_action_value(default=900)),
                "duration_ms": 500,
                "delay_seconds": 0.2,
            }
        return {"type": "tap"}

    def _float_action_value(self, default: float) -> float:
        try:
            return float(self.action_value)
        except ValueError:
            return default

    def _load_config(self) -> dict[str, Any]:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
                return json.load(file)
        return {"app": {}, "loop": {"interval_seconds": 1, "max_iterations": 300}, "scenarios": []}

    def _write_config(self, config: dict[str, Any]) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _script_names(self) -> list[str]:
        try:
            scenarios = self._load_config().get("scenarios", [])
        except (OSError, json.JSONDecodeError):
            scenarios = []
        names = {safe_template_name(str(scenario.get("script", "default"))) for scenario in scenarios}
        names.add(safe_template_name(self.script_name))
        return sorted(names)

    def _script_counts(self, scenarios: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for scenario in scenarios:
            name = safe_template_name(str(scenario.get("script", "default")))
            counts[name] = counts.get(name, 0) + 1
        return dict(sorted(counts.items()))

    def _visible_scenario_entries(self, scenarios: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
        script = safe_template_name(self.script_name)
        return [
            (index, scenario)
            for index, scenario in enumerate(scenarios)
            if safe_template_name(str(scenario.get("script", "default"))) == script
        ]

    def _clamp_scenario_cursor(self, count: int) -> None:
        if count <= 0:
            self.scenario_cursor = 0
        else:
            self.scenario_cursor = max(0, min(self.scenario_cursor, count - 1))

    def _selected_scenario_entry(self) -> Optional[tuple[dict[str, Any], int, dict[str, Any]]]:
        try:
            config = self._load_config()
        except (OSError, json.JSONDecodeError):
            return None
        scenarios = config.get("scenarios", [])
        entries = self._visible_scenario_entries(scenarios)
        self._clamp_scenario_cursor(len(entries))
        if not entries:
            return None
        scenario_index, scenario = entries[self.scenario_cursor]
        return config, scenario_index, scenario

    def select_scenario(self, direction: int) -> None:
        try:
            scenarios = self._load_config().get("scenarios", [])
        except (OSError, json.JSONDecodeError) as exc:
            self.status = f"Could not read scenarios.json: {exc}"
            return
        entries = self._visible_scenario_entries(scenarios)
        if not entries:
            self.status = "No scenario in this script."
            return
        self.scenario_cursor = (self.scenario_cursor + direction) % len(entries)
        self.status = f"Selected scenario: {entries[self.scenario_cursor][1].get('name', '')}"

    def select_scenario_by_config_index(self, scenario_index: int) -> None:
        try:
            scenarios = self._load_config().get("scenarios", [])
        except (OSError, json.JSONDecodeError) as exc:
            self.status = f"Could not read scenarios.json: {exc}"
            return
        entries = self._visible_scenario_entries(scenarios)
        for cursor, (config_index, scenario) in enumerate(entries):
            if config_index == scenario_index:
                self.scenario_cursor = cursor
                self.status = f"Selected scenario: {scenario.get('name', '')}"
                return

    def load_selected_scenario_to_form(self) -> None:
        selected = self._selected_scenario_entry()
        if not selected:
            self.status = "No scenario selected."
            return
        _config, _scenario_index, scenario = selected
        self.template_name = safe_template_name(str(scenario.get("name", self.template_name)))
        self.script_name = safe_template_name(str(scenario.get("script", self.script_name)))
        self._load_action_to_form(scenario.get("action", {}))
        self.status = f"Loaded scenario: {self.template_name}"

    def apply_form_to_selected_scenario(self) -> None:
        selected = self._selected_scenario_entry()
        if not selected:
            self.status = "No scenario selected."
            return
        config, scenario_index, scenario = selected
        scenario["name"] = safe_template_name(self.template_name)
        scenario["script"] = safe_template_name(self.script_name)
        scenario["action"] = self._build_selected_action()
        config["scenarios"][scenario_index] = scenario
        self._write_config(config)
        self.status = f"Updated scenario: {scenario['name']}"

    def insert_form_near_selected_scenario(self, before: bool) -> None:
        selected = self._selected_scenario_entry()
        if not selected:
            self.status = "No scenario selected."
            return

        scenario = self._build_form_scenario_for_insert()
        if not scenario:
            return

        config, selected_index, _selected_scenario = selected
        scenarios = config.setdefault("scenarios", [])
        scenario["name"] = self._unique_scenario_name(str(scenario.get("name", "scenario")), scenarios)
        insert_index = selected_index if before else selected_index + 1
        scenarios.insert(insert_index, scenario)
        self._write_config(config)

        entries = self._visible_scenario_entries(scenarios)
        for cursor, (config_index, _scenario) in enumerate(entries):
            if config_index == insert_index:
                self.scenario_cursor = cursor
                break
        where = "before" if before else "after"
        self.status = f"Inserted {where}: {scenario['name']}"

    def _unique_scenario_name(self, name: str, scenarios: list[dict[str, Any]]) -> str:
        existing = {str(scenario.get("name", "")) for scenario in scenarios}
        if name not in existing:
            return name
        base = f"{name}_copy"
        if base not in existing:
            return base
        for index in range(1, 1000):
            candidate = f"{base}_{index}"
            if candidate not in existing:
                return candidate
        return f"{base}_{int(time.time())}"

    def delete_selected_scenario(self) -> None:
        selected = self._selected_scenario_entry()
        if not selected:
            self.status = "No scenario selected."
            return
        config, scenario_index, scenario = selected
        name = scenario.get("name", "")
        del config["scenarios"][scenario_index]
        self._write_config(config)
        self._clamp_scenario_cursor(len(self._visible_scenario_entries(config.get("scenarios", []))))
        self.status = f"Deleted scenario: {name}"

    def _load_action_to_form(self, action: Any) -> None:
        if not isinstance(action, dict):
            self.action_mode_index = 0
            self.action_value = ""
            return
        action_type = action.get("type", "tap")
        if action_type == "tap_wait":
            self.action_mode_index = self._action_mode_index("tap_wait")
            self.action_value = str(action.get("seconds", 1))
        elif action_type == "tap_text":
            self.action_mode_index = self._action_mode_index("tap_text")
            self.action_value = str(action.get("text", "text"))
        elif action_type == "tap_swipe":
            direction = str(action.get("direction", "down"))
            mode = "tap_swipe_up" if direction == "up" else "tap_swipe_down"
            self.action_mode_index = self._action_mode_index(mode)
            self.action_value = str(action.get("distance", 900))
        else:
            self.action_mode_index = self._action_mode_index("tap")
            self.action_value = ""

    def _action_mode_index(self, mode: str) -> int:
        for index, (key, _label) in enumerate(ACTION_MODES):
            if key == mode:
                return index
        return 0

    def select_script(self, direction: int) -> None:
        scripts = self._script_names()
        if not scripts:
            self.script_name = "default"
            return
        current = safe_template_name(self.script_name)
        try:
            index = scripts.index(current)
        except ValueError:
            index = 0
        self.script_name = scripts[(index + direction) % len(scripts)]
        self.scenario_cursor = 0
        self.status = f"Selected script: {self.script_name}"

    def select_action(self, direction: int) -> None:
        self.action_mode_index = (self.action_mode_index + direction) % len(ACTION_MODES)
        mode, label = ACTION_MODES[self.action_mode_index]
        if mode == "tap":
            self.action_value = ""
        elif mode == "tap_wait":
            self.action_value = "1"
        elif mode == "tap_text":
            self.action_value = "text"
        else:
            self.action_value = "900"
        self.status = f"Selected action: {label}"

    def select_burst_count(self) -> None:
        self.burst_index = (self.burst_index + 1) % len(BURST_COUNTS)
        self.status = f"Burst count: {BURST_COUNTS[self.burst_index]}"

    def open_scenarios_file(self) -> None:
        """Open scenarios.json in the default Windows editor."""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not CONFIG_PATH.exists():
                self._write_config({"app": {}, "loop": {"interval_seconds": 1, "max_iterations": 300}, "scenarios": []})
            os.startfile(str(CONFIG_PATH))
            self.status = "Opened scenarios.json."
        except OSError as exc:
            self.status = f"Could not open scenarios.json: {exc}"

    def _automation_running(self) -> bool:
        return bool(self.automation_process and self.automation_process.poll() is None)

    def _append_automation_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        with self.automation_log_lock:
            self.automation_log_lines.append(line)
            self.automation_log_lines = self.automation_log_lines[-120:]
        if "Matched scenario=" in line:
            self.automation_matches += 1
            match = re.search(r"Matched scenario='([^']+)'", line)
            self.automation_current = match.group(1) if match else "matched"
            self.automation_status = "Running"
        elif "No scenario matched" in line:
            self.automation_no_matches += 1
            self.automation_current = "waiting for next match"
            self.automation_status = "Running"
        elif "Starting run" in line:
            self.automation_current = line.split("main:", 1)[-1].strip() if "main:" in line else line
            self.automation_status = "Running"
        elif "Report written:" in line:
            self.automation_current = "report written"
        elif "Automation finished." in line:
            self.automation_status = "Finished"

    def _read_automation_output(self, process: subprocess.Popen) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in stream:
                self._append_automation_line(str(line))
        except OSError as exc:
            self._append_automation_line(f"Log read error: {exc}")

    def _poll_automation_process(self) -> None:
        if not self.automation_process:
            return
        code = self.automation_process.poll()
        if code is None or self.automation_return_code == code:
            return
        self.automation_return_code = code
        if code == 0:
            self.automation_status = "Finished"
            self.status = "Automation finished."
        else:
            self.automation_status = f"Exited: {code}"
            self.status = f"Automation exited: {code}"

    def stop_automation(self) -> None:
        if not self._automation_running():
            self.status = "Automation is not running."
            return
        assert self.automation_process is not None
        self.automation_process.terminate()
        self.automation_status = "Stopping"
        self.status = "Stopping automation..."

    def run_automation(self) -> None:
        """Launch aos_game_auto.exe or main.py for the selected script."""
        if self._automation_running():
            self.stop_automation()
            return

        exe_path = APP_DIR / "aos_game_auto.exe"
        try:
            if exe_path.exists():
                command = [str(exe_path), "--config", str(CONFIG_PATH), "--script", safe_template_name(self.script_name), "--no-pause"]
            else:
                command = [
                    sys.executable,
                    str(APP_DIR / "main.py"),
                    "--config",
                    str(CONFIG_PATH),
                    "--script",
                    safe_template_name(self.script_name),
                    "--no-pause",
                ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.automation_log_lines = []
            self.automation_matches = 0
            self.automation_no_matches = 0
            self.automation_return_code = None
            self.automation_current = "-"
            self.automation_status = f"Starting: {safe_template_name(self.script_name)}"
            self.automation_process = subprocess.Popen(
                command,
                cwd=str(APP_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            threading.Thread(target=self._read_automation_output, args=(self.automation_process,), daemon=True).start()
            self.status = f"Automation started: {safe_template_name(self.script_name)}"
        except OSError as exc:
            self.status = f"Could not start automation: {exc}"


def main() -> int:
    TemplateCaptureWindow().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
