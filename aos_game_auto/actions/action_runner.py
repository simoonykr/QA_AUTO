import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from adb.adb_controller import AdbController
from vision.image_matcher import MatchResult


class ActionResult:
    """Result of one configured action execution."""

    def __init__(self, should_stop: bool = False, saved_screenshot_path: Optional[Path] = None):
        self.should_stop = should_stop
        self.saved_screenshot_path = saved_screenshot_path


class ActionRunner:
    """Executes configured actions using ADB and the current match result."""

    def __init__(self, adb: AdbController, screenshots_dir: Path):
        self.adb = adb
        self.screenshots_dir = screenshots_dir
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self, action: Dict[str, Any], match: MatchResult, current_screenshot: Path, iteration: int) -> ActionResult:
        action_type = action.get("type", "tap")
        self.logger.info("Running action '%s'", action_type)

        if action_type == "tap":
            x = match.center_x + int(action.get("offset_x", 0))
            y = match.center_y + int(action.get("offset_y", 0))
            self.adb.tap(x, y)
            wait_seconds = float(action.get("seconds", 0))
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            return ActionResult()

        if action_type == "tap_wait":
            x = match.center_x + int(action.get("offset_x", 0))
            y = match.center_y + int(action.get("offset_y", 0))
            self.adb.tap(x, y)
            time.sleep(float(action.get("seconds", 1)))
            return ActionResult()

        if action_type == "tap_text":
            x = match.center_x + int(action.get("offset_x", 0))
            y = match.center_y + int(action.get("offset_y", 0))
            self.adb.tap(x, y)
            time.sleep(float(action.get("delay_before_text", 0.3)))
            self.adb.input_text(str(action.get("text", "")))
            if action.get("press_enter", False):
                self.adb.keyevent("ENTER")
            wait_seconds = float(action.get("seconds", 0))
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            return ActionResult()

        if action_type == "tap_swipe":
            x = match.center_x + int(action.get("offset_x", 0))
            y = match.center_y + int(action.get("offset_y", 0))
            self.adb.tap(x, y)
            time.sleep(float(action.get("delay_seconds", 0.2)))
            distance = int(action.get("distance", 900))
            duration = int(action.get("duration_ms", 500))
            direction = str(action.get("direction", "down")).lower()
            if direction == "up":
                self.adb.swipe(x, y, x, max(0, y - distance), duration)
            else:
                self.adb.swipe(x, y, x, y + distance, duration)
            return ActionResult()

        if action_type == "double_tap":
            x = match.center_x + int(action.get("offset_x", 0))
            y = match.center_y + int(action.get("offset_y", 0))
            interval = float(action.get("interval_seconds", 0.12))
            self.adb.tap(x, y)
            time.sleep(interval)
            self.adb.tap(x, y)
            return ActionResult()

        if action_type == "swipe":
            self.adb.swipe(
                int(action["x1"]),
                int(action["y1"]),
                int(action["x2"]),
                int(action["y2"]),
                int(action.get("duration_ms", 500)),
            )
            return ActionResult()

        if action_type == "wait":
            time.sleep(float(action.get("seconds", 1)))
            return ActionResult()

        if action_type == "save_screenshot":
            saved_path = self._save_screenshot_copy(current_screenshot, iteration, "manual")
            return ActionResult(saved_screenshot_path=saved_path)

        if action_type == "stop":
            return ActionResult(should_stop=True)

        if action_type == "stop_and_save":
            saved_path = self._save_screenshot_copy(current_screenshot, iteration, "stop")
            return ActionResult(should_stop=True, saved_screenshot_path=saved_path)

        raise ValueError(f"Unsupported action type: {action_type}")

    def _save_screenshot_copy(self, current_screenshot: Path, iteration: int, reason: str) -> Path:
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        destination = self.screenshots_dir / f"saved_{reason}_{iteration:04d}_{int(time.time())}.png"
        shutil.copy2(current_screenshot, destination)
        return destination
