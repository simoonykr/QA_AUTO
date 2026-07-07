import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


class AdbError(RuntimeError):
    """Raised when an adb command fails."""


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    model: str = ""

    @property
    def label(self) -> str:
        suffix = f" ({self.model})" if self.model else ""
        return f"{self.serial}{suffix} [{self.state}]"


def parse_adb_devices(output: str) -> List[Device]:
    """Parse `adb devices -l` output into Device objects."""
    devices: List[Device] = []
    for raw_line in output.splitlines()[1:]:
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        serial, state = parts[0], parts[1]
        attributes = {}
        for part in parts[2:]:
            if ":" in part:
                key, value = part.split(":", 1)
                attributes[key] = value
        devices.append(Device(serial=serial, state=state, model=attributes.get("model", "")))
    return devices


class AdbController:
    """Small wrapper around adb commands used by the automation runner."""

    def __init__(self, adb_path: str = "adb", device_id: Optional[str] = None, timeout: int = 15):
        self.adb_path = adb_path
        self.device_id = device_id
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    def _base_command(self) -> List[str]:
        command = [self.adb_path]
        if self.device_id:
            command.extend(["-s", self.device_id])
        return command

    @staticmethod
    def _startupinfo() -> subprocess.STARTUPINFO | None:
        if not hasattr(subprocess, "STARTUPINFO"):
            return None
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return info

    def _run(self, args: Sequence[str], timeout: Optional[int] = None, binary: bool = False) -> subprocess.CompletedProcess:
        return self._run_once_with_reconnect(args, timeout=timeout, binary=binary, allow_reconnect=True)

    def _run_once_with_reconnect(
        self,
        args: Sequence[str],
        timeout: Optional[int] = None,
        binary: bool = False,
        allow_reconnect: bool = True,
    ) -> subprocess.CompletedProcess:
        command = self._base_command() + list(args)
        self.logger.debug("Running adb command: %s", " ".join(command))
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=not binary,
                timeout=timeout or self.timeout,
                startupinfo=self._startupinfo(),
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbError("adb executable was not found. Install Android Platform Tools and add adb to PATH.") from exc
        except PermissionError as exc:
            raise AdbError(
                f"Cannot execute adb path '{self.adb_path}'. "
                "Make sure this points to adb.exe, not a folder, and that Windows has not blocked the file."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb command timed out: {' '.join(command)}") from exc
        except OSError as exc:
            raise AdbError(f"Failed to execute adb path '{self.adb_path}': {exc}") from exc

        if result.returncode != 0:
            stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode(errors="replace")
            stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode(errors="replace")
            message = (stderr or stdout or "unknown adb error").strip()
            if allow_reconnect and "device" in message.lower() and "not found" in message.lower():
                previous_device_id = self.device_id
                self.logger.warning("ADB device disappeared. Refreshing device list and retrying once.")
                self.device_id = None
                time.sleep(0.5)
                self.ensure_device(preferred_device_id=previous_device_id)
                return self._run_once_with_reconnect(args, timeout=timeout, binary=binary, allow_reconnect=False)
            self.logger.error("ADB command failed: %s", message)
            raise AdbError(message)

        return result

    def list_device_infos(self) -> List[Device]:
        try:
            result = subprocess.run(
                [self.adb_path, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                startupinfo=self._startupinfo(),
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbError("adb executable was not found. Install Android Platform Tools and add adb to PATH.") from exc
        except PermissionError as exc:
            raise AdbError(
                f"Cannot execute adb path '{self.adb_path}'. "
                "Make sure this points to adb.exe, not a folder, and that Windows has not blocked the file."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError("adb devices command timed out.") from exc
        except OSError as exc:
            raise AdbError(f"Failed to execute adb path '{self.adb_path}': {exc}") from exc

        if result.returncode != 0:
            raise AdbError((result.stderr or result.stdout or "failed to list adb devices").strip())

        return parse_adb_devices(result.stdout)

    def list_devices(self) -> List[str]:
        return [device.serial for device in self.list_device_infos() if device.state == "device"]

    def online_devices(self) -> List[Device]:
        return [device for device in self.list_device_infos() if device.state == "device"]

    def ensure_device(self, preferred_device_id: Optional[str] = None, wait_seconds: float = 6.0) -> str:
        deadline = time.time() + wait_seconds
        last_devices: List[Device] = []
        target = preferred_device_id or self.device_id

        while True:
            last_devices = self.list_device_infos()
            online = [device for device in last_devices if device.state == "device"]

            if target:
                for device in online:
                    if device.serial == target:
                        self.device_id = device.serial
                        return self.device_id
                if time.time() >= deadline:
                    connected = ", ".join(device.label for device in last_devices) or "none"
                    raise AdbError(f"Configured device_id '{target}' is not online. Connected: {connected}")
            elif online:
                if len(online) > 1:
                    self.logger.warning(
                        "Multiple online adb devices found. Using first device: %s. All online devices: %s",
                        online[0].label,
                        ", ".join(device.label for device in online),
                    )
                self.device_id = online[0].serial
                return self.device_id

            if time.time() >= deadline:
                connected = ", ".join(device.label for device in last_devices) or "none"
                if any(device.state == "unauthorized" for device in last_devices):
                    raise AdbError(f"ADB device is unauthorized. Allow USB debugging on the device. Connected: {connected}")
                if any(device.state == "offline" for device in last_devices):
                    raise AdbError(f"ADB device is offline. Reconnect USB or run adb kill-server/start-server. Connected: {connected}")
                raise AdbError(f"No online adb device found. Connected: {connected}")

            self.logger.info("Waiting for an online adb device. Current: %s", ", ".join(device.label for device in last_devices) or "none")
            time.sleep(0.75)

    def get_resolution(self) -> Tuple[int, int]:
        result = self._run(["shell", "wm", "size"])
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", result.stdout)
        if not match:
            raise AdbError(f"Could not parse device resolution from: {result.stdout.strip()}")
        return int(match.group(1)), int(match.group(2))

    def capture_screen(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        last_error = ""
        for attempt in range(1, 4):
            result = self._run(["exec-out", "screencap", "-p"], timeout=30, binary=True)
            data = result.stdout
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                output_path.write_bytes(data)
                return output_path
            last_error = f"invalid PNG data from screencap on attempt {attempt}"
            self.logger.warning("%s", last_error)
            time.sleep(0.3)
        raise AdbError(f"Failed to capture a valid PNG screenshot: {last_error}")

    def list_user_packages(self) -> List[str]:
        """Return sorted third-party package names installed on the device."""
        result = self._run(["shell", "pm", "list", "packages", "-3"], timeout=30)
        packages: List[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line.split("package:", 1)[1].strip())
        return sorted(package for package in packages if package)

    def get_foreground_app(self) -> Tuple[str, str]:
        """Return package and activity for the currently focused app when Android exposes it."""
        result = self._run(["shell", "dumpsys", "window"], timeout=30)
        text = result.stdout
        patterns = [
            r"mCurrentFocus=.*?\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)",
            r"mFocusedApp=.*?\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                package, activity = match.group(1), match.group(2)
                if activity.startswith("."):
                    activity = f"{package}{activity}"
                return package, activity
        raise AdbError("Could not detect the foreground app from dumpsys window.")

    def tap(self, x: int, y: int) -> None:
        self._run(["shell", "input", "tap", str(x), str(y)])

    def input_text(self, text: str) -> None:
        """Type text through adb input. Spaces are escaped for Android input."""
        escaped = text.replace("\\", "\\\\").replace(" ", "%s")
        self._run(["shell", "input", "text", escaped])

    def keyevent(self, key: str) -> None:
        self._run(["shell", "input", "keyevent", key])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
        self._run(
            ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)]
        )

    def start_app(self, package: str, activity: str) -> None:
        component = f"{package}/{activity}"
        self._run(["shell", "am", "start", "-n", component], timeout=20)

    def start_package(self, package: str) -> None:
        """Launch an app through its launcher intent using only a package name."""
        self._run(
            ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
            timeout=20,
        )

    def stop_app(self, package: str) -> None:
        self._run(["shell", "am", "force-stop", package], timeout=20)
