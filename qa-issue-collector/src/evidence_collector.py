import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
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
    pre_log_seconds: int
    post_log_seconds: int
    record_video: bool
    video_seconds: int


class EvidenceCollector:
    def __init__(self, project_root, adb_client):
        self.project_root = Path(project_root)
        self.adb = adb_client
        self.issues_dir = self.project_root / "data" / "issues"

    def collect(self, draft, progress=None):
        anchor_time = datetime.now()
        issue_dir = self.create_issue_dir(draft.summary)
        self.emit(progress, f"이슈 폴더 생성: {issue_dir}")

        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "issue": asdict(draft),
            "device": self.adb.get_device_info(draft.device_id),
            "app": self.adb.get_app_info(draft.device_id, draft.package_name),
            "files": {},
        }

        file_stem = self.safe_name(draft.summary, limit=80)
        video_error = []
        video_thread = None

        if draft.record_video:
            video_path = issue_dir / f"{file_stem}.mp4"
            metadata["files"]["screenrecord"] = str(video_path)
            self.emit(progress, f"버튼 시점 이후 {draft.video_seconds}초 화면 녹화를 시작합니다.")

            def record_video():
                try:
                    self.adb.record_screen(draft.device_id, video_path, seconds=draft.video_seconds)
                except Exception as exc:
                    video_error.append(exc)

            video_thread = threading.Thread(target=record_video, daemon=True)
            video_thread.start()

        before_log_path = issue_dir / f"{file_stem}_before.txt"
        self.emit(progress, f"버튼 시점 이전 {draft.pre_log_seconds}초 logcat 수집 중...")
        before_log_count = self.adb.collect_logcat_between(
            draft.device_id,
            before_log_path,
            anchor_time - timedelta(seconds=draft.pre_log_seconds),
            anchor_time,
            package_name=draft.package_name,
        )
        metadata["files"]["logcat_before"] = str(before_log_path)
        metadata["log_before_count"] = before_log_count

        screenshot_path = issue_dir / f"{file_stem}.png"
        self.emit(progress, "스크린샷 저장 중...")
        self.adb.capture_screenshot(draft.device_id, screenshot_path)
        metadata["files"]["screenshot"] = str(screenshot_path)

        after_end_time = anchor_time + timedelta(seconds=draft.post_log_seconds)
        remaining = (after_end_time - datetime.now()).total_seconds()
        if remaining > 0:
            self.emit(progress, f"버튼 시점 이후 {draft.post_log_seconds}초 logcat 대기 중...")
            time.sleep(remaining)

        after_log_path = issue_dir / f"{file_stem}_after.txt"
        self.emit(progress, f"버튼 시점 이후 {draft.post_log_seconds}초 logcat 수집 중...")
        after_log_count = self.adb.collect_logcat_between(
            draft.device_id,
            after_log_path,
            anchor_time,
            after_end_time,
            package_name=draft.package_name,
        )
        metadata["files"]["logcat_after"] = str(after_log_path)
        metadata["log_after_count"] = after_log_count

        if video_thread:
            video_thread.join()
            if video_error:
                raise video_error[0]

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
        safe_summary = self.safe_name(summary, limit=50)
        issue_dir = self.issues_dir / f"{timestamp}_{safe_summary}"
        issue_dir.mkdir(parents=True, exist_ok=False)
        return issue_dir

    def safe_name(self, text, limit=80):
        safe_text = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in text)
        return "_".join(safe_text.split())[:limit] or "issue"

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
- 이전 로그: {files.get("logcat_before", "")}
- 이후 로그: {files.get("logcat_after", "")}
- 스크린샷: {files.get("screenshot", "")}
- 영상: {files.get("screenrecord", "")}
"""

    def emit(self, progress, message):
        if progress:
            progress(message)
