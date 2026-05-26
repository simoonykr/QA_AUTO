import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class IssueDraft:
    summary: str
    steps: str
    actual_result: str
    expected_result: str
    severity: str
    package_name: str
    device_id: str
    log_seconds: int
    record_video: bool
    video_seconds: int


class EvidenceCollector:
    def __init__(self, project_root, adb_client):
        self.project_root = Path(project_root)
        self.adb = adb_client
        self.issues_dir = self.project_root / "data" / "issues"

    def collect(self, draft, progress=None):
        issue_dir = self.create_issue_dir(draft.summary)
        self.emit(progress, f"이슈 폴더 생성: {issue_dir}")

        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "issue": asdict(draft),
            "device": self.adb.get_device_info(draft.device_id),
            "app": self.adb.get_app_info(draft.device_id, draft.package_name),
            "files": {},
        }

        log_path = issue_dir / "logcat.txt"
        self.emit(progress, "logcat 수집 중...")
        log_count = self.adb.collect_logcat(
            draft.device_id,
            log_path,
            package_name=draft.package_name,
            seconds=draft.log_seconds,
        )
        metadata["files"]["logcat"] = str(log_path)
        metadata["log_count"] = log_count

        screenshot_path = issue_dir / "screenshot.png"
        self.emit(progress, "스크린샷 저장 중...")
        self.adb.capture_screenshot(draft.device_id, screenshot_path)
        metadata["files"]["screenshot"] = str(screenshot_path)

        if draft.record_video:
            video_path = issue_dir / "screenrecord.mp4"
            self.emit(progress, f"{draft.video_seconds}초 화면 녹화 중...")
            self.adb.record_screen(draft.device_id, video_path, seconds=draft.video_seconds)
            metadata["files"]["screenrecord"] = str(video_path)

        metadata_path = issue_dir / "issue_meta.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        metadata["files"]["metadata"] = str(metadata_path)

        summary_path = issue_dir / "issue_summary.md"
        summary_path.write_text(self.render_summary(metadata), encoding="utf-8")
        metadata["files"]["summary"] = str(summary_path)

        self.emit(progress, "증거 수집 완료")
        return issue_dir, metadata

    def create_issue_dir(self, summary):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_summary = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in summary)
        safe_summary = "_".join(safe_summary.split())[:50] or "issue"
        issue_dir = self.issues_dir / f"{timestamp}_{safe_summary}"
        issue_dir.mkdir(parents=True, exist_ok=False)
        return issue_dir

    def render_summary(self, metadata):
        issue = metadata["issue"]
        device = metadata["device"]
        app = metadata["app"]
        files = metadata["files"]

        return f"""# {issue["summary"]}

## 기본 정보
- 생성 시각: {metadata["created_at"]}
- 심각도: {issue["severity"]}
- 패키지: {issue["package_name"]}
- 앱 버전: {app.get("version_name", "")} ({app.get("version_code", "")})
- 디바이스: {device.get("manufacturer", "")} {device.get("model", "")}
- Android: {device.get("android_version", "")} / SDK {device.get("sdk", "")}

## 재현 절차
{issue["steps"]}

## 실제 결과
{issue["actual_result"]}

## 기대 결과
{issue["expected_result"]}

## 첨부 파일
- 로그: {files.get("logcat", "")}
- 스크린샷: {files.get("screenshot", "")}
- 영상: {files.get("screenrecord", "")}
"""

    def emit(self, progress, message):
        if progress:
            progress(message)
