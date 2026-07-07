import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class AppInfo:
    package: str
    label: str

    @property
    def display_name(self):
        if self.label and self.label != self.package:
            return f"{self.label} ({self.package})"
        return self.package


class AdbError(RuntimeError):
    pass


class AdbClient:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.config_path = self.project_root / "config" / "settings.json"
        self.label_cache_path = self.project_root / "data" / "app_label_cache.json"
        self.apk_cache_dir = Path(tempfile.gettempdir()) / "qa_issue_collector" / "apk_cache"
        self.adb_path = self.load_adb_path()
        self.aapt_path = self.load_aapt_path()
        self.label_cache = self.load_label_cache()

    def load_adb_path(self):
        configured_path = self.read_config().get("adb_path")
        if configured_path and Path(configured_path).exists():
            return configured_path

        candidates = [
            Path(os.getenv("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(os.getenv("USERPROFILE", "")) / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path("adb.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                self.save_adb_path(str(candidate))
                return str(candidate)

        return "adb.exe"

    def read_config(self):
        if not self.config_path.exists():
            return {}
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def save_adb_path(self, adb_path):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.read_config()
        data["adb_path"] = adb_path
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.adb_path = adb_path

    def load_aapt_path(self):
        configured_path = self.read_config().get("aapt_path")
        if configured_path and Path(configured_path).exists():
            return configured_path

        sdk_root = Path(os.getenv("LOCALAPPDATA", "")) / "Android" / "Sdk"
        build_tools = sdk_root / "build-tools"
        if build_tools.exists():
            candidates = sorted(build_tools.glob("*/aapt.exe"), reverse=True)
            if candidates:
                aapt_path = str(candidates[0])
                data = self.read_config()
                data["aapt_path"] = aapt_path
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with self.config_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return aapt_path

        return ""

    def load_label_cache(self):
        if not self.label_cache_path.exists():
            return {}
        try:
            with self.label_cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def save_label_cache(self):
        self.label_cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.label_cache_path.open("w", encoding="utf-8") as f:
            json.dump(self.label_cache, f, ensure_ascii=False, indent=2)

    def run(self, args, timeout=20, check=False):
        try:
            result = subprocess.run(
                [self.adb_path, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise AdbError("ADB 실행 파일을 찾을 수 없습니다. ADB 경로를 설정해주세요.") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError("ADB 명령 시간이 초과되었습니다.") from exc

        command_result = CommandResult(result.returncode, result.stdout, result.stderr)
        if check and result.returncode != 0:
            raise AdbError(result.stderr.strip() or "ADB 명령 실행에 실패했습니다.")
        return command_result

    def shell(self, device_id, command, timeout=20, check=False):
        return self.run(["-s", device_id, "shell", *command], timeout=timeout, check=check)

    def list_devices(self):
        result = self.run(["devices"], check=True)
        devices = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def list_packages(self, device_id):
        result = self.shell(device_id, ["pm", "list", "packages"], check=True)
        packages = []
        for line in result.stdout.splitlines():
            if line.startswith("package:"):
                packages.append(line.replace("package:", "", 1).strip())
        return sorted(packages)

    def list_apps(self, device_id):
        apps = []
        packages = self.list_launchable_packages(device_id)
        if not packages:
            packages = self.list_packages(device_id)
        for package in packages:
            apps.append(AppInfo(package=package, label=self.get_app_label(device_id, package)))
        return sorted(apps, key=lambda app: app.display_name.lower())

    def list_launchable_packages(self, device_id):
        result = self.shell(
            device_id,
            [
                "cmd",
                "package",
                "query-activities",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
            ],
            timeout=30,
        )
        if result.returncode != 0:
            return []

        packages = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if "/" not in line or line.startswith("Activity #"):
                continue
            package = line.split("/", 1)[0].strip()
            if package:
                packages.add(package)
        return sorted(packages)

    def list_running_processes(self, device_id):
        result = self.shell(device_id, ["ps", "-A"])
        if result.returncode != 0:
            result = self.shell(device_id, ["ps"], check=True)

        processes = set()
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if parts:
                name = parts[-1]
                if "." in name and not name.startswith("["):
                    processes.add(name)
        return sorted(processes)

    def list_running_apps(self, device_id):
        apps = []
        launchable_packages = set(self.list_launchable_packages(device_id))
        running_packages = self.list_running_processes(device_id)
        if launchable_packages:
            running_packages = [package for package in running_packages if package in launchable_packages]
        for package in running_packages:
            apps.append(AppInfo(package=package, label=self.get_app_label(device_id, package)))
        return sorted(apps, key=lambda app: app.display_name.lower())

    def get_app_label(self, device_id, package_name):
        if package_name in self.label_cache and self.label_cache[package_name] != package_name:
            return self.label_cache[package_name]

        label = self.get_app_label_from_dumpsys(device_id, package_name)
        if label != package_name:
            self.label_cache[package_name] = label
            self.save_label_cache()
            return label

        label = self.get_app_label_from_apk(device_id, package_name)
        self.label_cache[package_name] = label
        self.save_label_cache()
        return label

    def get_app_label_from_dumpsys(self, device_id, package_name):
        result = self.shell(device_id, ["dumpsys", "package", package_name], timeout=20)
        if result.returncode != 0:
            return package_name

        label_patterns = [
            r"application-label(?:-[^:]+)?:'([^']+)'",
            r'nonLocalizedLabel=([^,\s}]+)',
        ]
        for pattern in label_patterns:
            match = re.search(pattern, result.stdout)
            if match:
                label = match.group(1).strip()
                if label:
                    return label
        return package_name

    def get_app_label_from_apk(self, device_id, package_name):
        if not self.aapt_path:
            return package_name

        apk_path = self.get_package_apk_path(device_id, package_name)
        if not apk_path:
            return package_name

        self.apk_cache_dir.mkdir(parents=True, exist_ok=True)
        local_apk = self.apk_cache_dir / f"{self.safe_filename(package_name)}.apk"
        pull_result = self.run(["-s", device_id, "pull", apk_path, str(local_apk)], timeout=60)
        if pull_result.returncode != 0 or not local_apk.exists():
            return package_name

        try:
            result = subprocess.run(
                [self.aapt_path, "dump", "badging", str(local_apk)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return package_name

        for pattern in (
            r"application-label-ko:'([^']+)'",
            r"application-label:'([^']+)'",
            r"application-label-[^:]+:'([^']+)'",
        ):
            match = re.search(pattern, result.stdout)
            if match:
                label = match.group(1).strip()
                if label:
                    return label

        return package_name

    def get_package_apk_path(self, device_id, package_name):
        result = self.shell(device_id, ["pm", "path", package_name], timeout=20)
        if result.returncode != 0:
            return ""

        paths = []
        for line in result.stdout.splitlines():
            if line.startswith("package:"):
                paths.append(line.replace("package:", "", 1).strip())
        for path in paths:
            if path.endswith("/base.apk"):
                return path
        return paths[0] if paths else ""

    def safe_filename(self, value):
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)

    def get_pid(self, device_id, package_name):
        result = self.shell(device_id, ["pidof", package_name])
        if result.returncode != 0:
            return []
        return result.stdout.strip().split()

    def get_device_info(self, device_id):
        props = {
            "model": ["getprop", "ro.product.model"],
            "manufacturer": ["getprop", "ro.product.manufacturer"],
            "android_version": ["getprop", "ro.build.version.release"],
            "sdk": ["getprop", "ro.build.version.sdk"],
            "build_id": ["getprop", "ro.build.display.id"],
        }
        info = {"device_id": device_id}
        for key, command in props.items():
            result = self.shell(device_id, command)
            info[key] = result.stdout.strip()
        return info

    def get_app_info(self, device_id, package_name):
        result = self.shell(device_id, ["dumpsys", "package", package_name], timeout=30)
        info = {"package": package_name, "label": self.get_app_label(device_id, package_name)}
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("versionName="):
                info["version_name"] = stripped.split("=", 1)[1]
            elif stripped.startswith("versionCode="):
                info["version_code"] = stripped.split("=", 1)[1].split()[0]
        return info

    def capture_screenshot(self, device_id, output_path):
        with Path(output_path).open("wb") as f:
            result = subprocess.run(
                [self.adb_path, "-s", device_id, "exec-out", "screencap", "-p"],
                stdout=f,
                stderr=subprocess.PIPE,
                timeout=20,
            )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise AdbError(message or "스크린샷 저장에 실패했습니다.")

    def record_screen(self, device_id, output_path, seconds=10):
        remote_path = "/sdcard/qa_issue_record.mp4"
        self.shell(device_id, ["rm", "-f", remote_path])
        self.shell(device_id, ["screenrecord", "--time-limit", str(seconds), remote_path], timeout=seconds + 10, check=True)
        self.run(["-s", device_id, "pull", remote_path, str(output_path)], timeout=60, check=True)
        self.shell(device_id, ["rm", "-f", remote_path])

    def collect_logcat(self, device_id, output_path, package_name=None, seconds=30):
        args = ["-s", device_id, "logcat", "-v", "threadtime", "-d"]
        result = self.run(args, timeout=40, check=True)
        lines = result.stdout.splitlines()

        if package_name:
            pids = set(self.get_pid(device_id, package_name))
            if pids:
                lines = [line for line in lines if self.line_has_pid(line, pids)]

        filtered = self.filter_recent_threadtime(lines, seconds)
        Path(output_path).write_text("\n".join(filtered) + "\n", encoding="utf-8")
        return len(filtered)

    def collect_logcat_between(self, device_id, output_path, start_time, end_time, package_name=None):
        args = ["-s", device_id, "logcat", "-v", "threadtime", "-d"]
        result = self.run(args, timeout=40, check=True)
        lines = result.stdout.splitlines()

        if package_name:
            pids = set(self.get_pid(device_id, package_name))
            if pids:
                lines = [line for line in lines if self.line_has_pid(line, pids)]

        filtered = self.filter_threadtime_between(lines, start_time, end_time)
        Path(output_path).write_text("\n".join(filtered) + "\n", encoding="utf-8")
        return len(filtered)

    def line_has_pid(self, line, pids):
        parts = line.split(maxsplit=5)
        return len(parts) >= 3 and parts[2] in pids

    def filter_recent_threadtime(self, lines, seconds):
        from datetime import datetime, timedelta

        start_time = datetime.now() - timedelta(seconds=seconds)
        return self.filter_threadtime_between(lines, start_time, datetime.now())

    def filter_threadtime_between(self, lines, start_time, end_time):
        from datetime import datetime

        filtered = []
        for line in lines:
            parts = line.split(maxsplit=5)
            if len(parts) < 6:
                continue
            try:
                log_time = datetime.strptime(
                    f"{datetime.now().year}-{parts[0]} {parts[1]}",
                    "%Y-%m-%d %H:%M:%S.%f",
                )
            except ValueError:
                continue
            if start_time <= log_time <= end_time:
                filtered.append(line)
        return filtered
