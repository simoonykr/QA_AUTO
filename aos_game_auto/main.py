import argparse
import csv
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from actions.action_runner import ActionRunner
from adb.adb_controller import AdbController, AdbError
from vision.image_matcher import ImageMatcher, MatchResult


def get_app_dir() -> Path:
    """Return the editable app directory for both Python and frozen exe runs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PROJECT_DIR = get_app_dir()
DEFAULT_CONFIG = PROJECT_DIR / "config" / "scenarios.json"
LOGS_DIR = PROJECT_DIR / "logs"
SCREENSHOTS_DIR = PROJECT_DIR / "screenshots"
REPORTS_DIR = PROJECT_DIR / "reports"


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, encoding="utf-8")],
    )


def load_config(config_path: Path) -> Dict[str, Any]:
    try:
        with config_path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config JSON parse failed: {config_path} ({exc})") from exc
    except OSError as exc:
        raise ValueError(f"Could not read config file: {config_path} ({exc})") from exc


def _resolve_adb_candidate(path: Path, adb_names: list[str]) -> Optional[Path]:
    """Return an executable adb file from a file or directory candidate."""
    if _is_file(path):
        return path
    if _is_dir(path):
        for name in adb_names:
            candidate = path / name
            if _is_file(candidate):
                return candidate
    return None


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


def resolve_adb_path(adb_arg: str) -> str:
    """Find adb from CLI arg, exe folder, common SDK paths, or PATH."""
    requested = Path(adb_arg)
    if requested.name.lower() == "adb" and requested.suffix == "":
        adb_names = ["adb.exe", "adb"]
    else:
        adb_names = [requested.name]

    requested_match = _resolve_adb_candidate(requested, adb_names)
    if requested_match:
        return str(requested_match)

    candidates = []
    for name in adb_names:
        candidates.extend(
            [
                PROJECT_DIR / name,
                PROJECT_DIR / "platform-tools" / name,
            ]
        )

    for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        env_value = os.environ.get(env_name)
        if env_value:
            for name in adb_names:
                candidates.append(Path(env_value) / "platform-tools" / name)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for name in adb_names:
            candidates.append(Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / name)

    home = Path.home()
    downloads = home / "Downloads"
    if downloads.exists():
        for name in adb_names:
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


def resolve_tesseract_path(tesseract_arg: str) -> str:
    """Find tesseract.exe from CLI arg, environment, common install paths, or PATH."""
    candidates: list[Path] = []
    if tesseract_arg:
        candidates.append(Path(tesseract_arg))

    env_value = os.environ.get("TESSERACT_CMD")
    if env_value:
        candidates.append(Path(env_value))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe")

    candidates.extend(
        [
            Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
            Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        ]
    )

    for candidate in candidates:
        if _is_file(candidate):
            return str(candidate)

    path_match = shutil.which("tesseract")
    if path_match and _is_file(Path(path_match)):
        return path_match

    return tesseract_arg


def pause_on_fatal_exit() -> None:
    """Keep a double-clicked Windows exe window open long enough to read the error."""
    if getattr(sys, "frozen", False) and os.environ.get("AOS_AUTO_NO_PAUSE") != "1":
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass


def open_csv_log() -> tuple[Path, Any, csv.DictWriter]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file = path.open("w", newline="", encoding="utf-8-sig")
    fieldnames = [
        "time",
        "run_index",
        "iteration",
        "scenario_name",
        "match_type",
        "matched_text",
        "template_path",
        "match_score",
        "match_x",
        "match_y",
        "action",
        "success",
        "message",
        "screenshot_path",
        "saved_screenshot_path",
    ]
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    return path, file, writer


def write_iteration_log(
    writer: csv.DictWriter,
    run_index: int,
    iteration: int,
    screenshot_path: Path,
    match: Optional[MatchResult],
    action: Optional[Dict[str, Any]],
    success: bool,
    message: str = "",
    saved_screenshot_path: Optional[Path] = None,
) -> None:
    writer.writerow(
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "run_index": run_index,
            "iteration": iteration,
            "scenario_name": match.scenario.get("name", "") if match else "",
            "match_type": match.match_type if match else "",
            "matched_text": match.matched_text if match else "",
            "template_path": str(match.template_path) if match else "",
            "match_score": f"{match.score:.4f}" if match else "",
            "match_x": match.center_x if match else "",
            "match_y": match.center_y if match else "",
            "action": json.dumps(action or {}, ensure_ascii=False),
            "success": success,
            "message": message,
            "screenshot_path": str(screenshot_path),
            "saved_screenshot_path": str(saved_screenshot_path or ""),
        }
    )


def create_markdown_report(
    result_log_path: Path,
    config: Dict[str, Any],
    active_config: Dict[str, Any],
    script_name: Optional[str],
    started_at: datetime,
    finished_at: datetime,
    finish_reason: str,
) -> Path:
    """Create a human-readable automation summary from the CSV result log."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[Dict[str, str]] = []
    with result_log_path.open("r", newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    total = len(rows)
    matched_rows = [row for row in rows if row.get("scenario_name")]
    no_match_rows = [row for row in rows if row.get("message") == "no match"]
    failed_rows = [row for row in rows if str(row.get("success", "")).lower() not in ("true", "1", "yes")]
    run_indices = sorted({row.get("run_index", "") for row in rows if row.get("run_index", "")})

    scenario_stats: dict[str, dict[str, Any]] = {}
    action_counts: dict[str, int] = {}
    for row in matched_rows:
        name = row.get("scenario_name", "unnamed") or "unnamed"
        stats = scenario_stats.setdefault(
            name,
            {"count": 0, "scores": [], "templates": set(), "actions": set(), "match_types": set(), "texts": set()},
        )
        stats["count"] += 1
        if row.get("template_path"):
            stats["templates"].add(row["template_path"])
        if row.get("match_type"):
            stats["match_types"].add(row["match_type"])
        if row.get("matched_text"):
            stats["texts"].add(row["matched_text"])
        try:
            stats["scores"].append(float(row.get("match_score", "")))
        except ValueError:
            pass

        action_text = row.get("action", "{}")
        try:
            action = json.loads(action_text)
            action_type = str(action.get("type", "unknown"))
        except json.JSONDecodeError:
            action_type = "unknown"
        stats["actions"].add(action_type)
        action_counts[action_type] = action_counts.get(action_type, 0) + 1

    scores = [score for stats in scenario_stats.values() for score in stats["scores"]]
    duration = finished_at - started_at
    app_config = config.get("app", {})
    package = app_config.get("package", "")
    activity = app_config.get("activity", "")
    report_path = REPORTS_DIR / f"report_{finished_at.strftime('%Y%m%d_%H%M%S')}.md"

    lines = [
        "# AOS Automation Report",
        "",
        "## Summary",
        "",
        f"- Started: {started_at.isoformat(timespec='seconds')}",
        f"- Finished: {finished_at.isoformat(timespec='seconds')}",
        f"- Duration: {duration}",
        f"- Finish reason: {finish_reason}",
        f"- Script: {script_name or 'all'}",
        f"- App package: {package or '(not set)'}",
        f"- App activity: {activity or '(not set)'}",
        f"- Configured scenarios: {len(active_config.get('scenarios', []))}",
        f"- Completed runs: {len(run_indices)}",
        f"- Total iterations: {total}",
        f"- Matched iterations: {len(matched_rows)}",
        f"- No-match iterations: {len(no_match_rows)}",
        f"- Failed iterations: {len(failed_rows)}",
        f"- Best score: {max(scores):.4f}" if scores else "- Best score: N/A",
        f"- Average score: {sum(scores) / len(scores):.4f}" if scores else "- Average score: N/A",
        f"- CSV log: {result_log_path}",
        "",
        "## Scenario Results",
        "",
        "| Scenario | Hits | Type | Best | Avg | Actions | Templates |",
        "|---|---:|---|---:|---:|---|---:|",
    ]

    if scenario_stats:
        for name, stats in sorted(scenario_stats.items()):
            scenario_scores = stats["scores"]
            best = f"{max(scenario_scores):.4f}" if scenario_scores else "N/A"
            avg = f"{sum(scenario_scores) / len(scenario_scores):.4f}" if scenario_scores else "N/A"
            actions = ", ".join(sorted(stats["actions"])) or "-"
            match_types = ", ".join(sorted(stats["match_types"])) or "-"
            lines.append(f"| {name} | {stats['count']} | {match_types} | {best} | {avg} | {actions} | {len(stats['templates'])} |")
    else:
        lines.append("| (none) | 0 | - | N/A | N/A | - | 0 |")

    lines.extend(["", "## Action Counts", ""])
    if action_counts:
        for action_type, count in sorted(action_counts.items()):
            lines.append(f"- {action_type}: {count}")
    else:
        lines.append("- No actions executed.")

    lines.extend(
        [
            "",
            "## Matched Iterations",
            "",
            "| Run | Iteration | Scenario | Type | Score | Center | Action | Match |",
            "|---:|---:|---|---|---:|---|---|---|",
        ]
    )
    for row in matched_rows[-30:]:
        center = f"({row.get('match_x', '')}, {row.get('match_y', '')})"
        action_type = "unknown"
        try:
            action_type = str(json.loads(row.get("action", "{}")).get("type", "unknown"))
        except json.JSONDecodeError:
            pass
        template_name = Path(row.get("template_path", "")).name
        match_label = row.get("matched_text", "") or template_name
        lines.append(
            f"| {row.get('run_index', '')} | {row.get('iteration', '')} | {row.get('scenario_name', '')} | {row.get('match_type', '')} | "
            f"{row.get('match_score', '')} | {center} | {action_type} | {match_label} |"
        )
    if not matched_rows:
        lines.append("| - | - | - | - | - | - | - | - |")

    if failed_rows:
        lines.extend(["", "## Failures", "", "| Iteration | Message | Screenshot |", "|---:|---|---|"])
        for row in failed_rows[-20:]:
            lines.append(f"| {row.get('iteration', '')} | {row.get('message', '')} | {row.get('screenshot_path', '')} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- If no-match count is high, recapture smaller and more stable templates.",
            "- Avoid animated backgrounds, changing numbers, and large character/scene areas in templates.",
            "- For expected popups or screen transitions, add the next screen as another scenario.",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def validate_templates(config: Dict[str, Any], base_dir: Path) -> list[Path]:
    """Return configured template paths that are missing or not PNG-looking files."""
    invalid_paths: list[Path] = []
    for scenario in config.get("scenarios", []):
        if scenario.get("enabled", True) is False:
            continue

        for template_value in scenario_template_values(scenario):
            template_path = Path(template_value)
            if not template_path.is_absolute():
                template_path = base_dir / template_path

            if not template_path.exists() or template_path.stat().st_size == 0:
                invalid_paths.append(template_path)
                continue

            try:
                with template_path.open("rb") as file:
                    if not file.read(8).startswith(b"\x89PNG"):
                        invalid_paths.append(template_path)
            except OSError:
                    invalid_paths.append(template_path)
    return invalid_paths


def scenario_template_values(scenario: Dict[str, Any]) -> list[str]:
    """Return every template path referenced by legacy, match, or match_any config."""
    values: list[str] = []

    def add_from(config: Dict[str, Any]) -> None:
        if str(config.get("type", "template")).lower() == "ocr":
            return
        templates_value = config.get("templates")
        if isinstance(templates_value, list):
            values.extend(str(value) for value in templates_value if value)
        template_value = config.get("template")
        if template_value:
            template_text = str(template_value)
            if template_text not in values:
                values.append(template_text)

    match_any = scenario.get("match_any")
    if isinstance(match_any, list):
        for match_config in match_any:
            if isinstance(match_config, dict):
                add_from(match_config)
        return values

    match_value = scenario.get("match")
    if isinstance(match_value, dict):
        add_from(match_value)
        return values

    add_from(scenario)
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AOS game QA automation MVP using ADB and OpenCV.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to scenarios.json")
    parser.add_argument("--adb", default="adb", help="Path to adb executable")
    parser.add_argument("--device", default=None, help="ADB device id. Defaults to first connected device.")
    parser.add_argument("--script", default=None, help="Run only scenarios with this script name. Missing script fields are 'default'.")
    parser.add_argument("--list-devices", action="store_true", help="Print adb devices and exit.")
    parser.add_argument("--skip-start-app", action="store_true", help="Do not launch app before loop.")
    parser.add_argument("--capture-only", action="store_true", help="Capture one screenshot and exit.")
    parser.add_argument("--runs", type=int, default=1, help="Repeat the selected script this many times.")
    parser.add_argument("--monitor-minutes", type=float, default=0, help="Repeat script runs until this many minutes have elapsed.")
    parser.add_argument("--monitor-hours", type=float, default=0, help="Repeat script runs until this many hours have elapsed.")
    parser.add_argument(
        "--run-mode",
        choices=["scan", "sequence"],
        default=None,
        help="scan: match all scenarios every loop. sequence: continue after the last matched scenario.",
    )
    parser.add_argument("--tesseract-cmd", default="", help="Path to tesseract.exe for OCR scenarios.")
    parser.add_argument(
        "--allow-missing-templates",
        action="store_true",
        help="Start even when configured template files are missing.",
    )
    parser.add_argument(
        "--strict-templates",
        action="store_true",
        help="Fail immediately when configured template files are missing.",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Do not wait for Enter on fatal errors. Useful when launched from the GUI.",
    )
    return parser


def main() -> int:
    setup_logging()
    logger = logging.getLogger("main")
    args = build_parser().parse_args()
    if args.no_pause:
        os.environ["AOS_AUTO_NO_PAUSE"] = "1"
    started_at = datetime.now()
    finish_reason = "not started"

    try:
        config_path = Path(args.config).resolve()
        config = load_config(config_path)
    except ValueError as exc:
        logger.error("%s", exc)
        pause_on_fatal_exit()
        return 2

    if not args.script:
        loop_config = config.get("loop", {})
        default_script = config.get("default_script") or loop_config.get("default_script")
        if default_script:
            args.script = str(default_script)
            logger.info("Using default script from config: %s", args.script)

    active_config = config
    if args.script:
        active_scenarios = [
            scenario for scenario in config.get("scenarios", []) if scenario.get("script", "default") == args.script
        ]
        active_config = {**config, "scenarios": active_scenarios}

    invalid_templates = validate_templates(active_config, PROJECT_DIR)
    should_auto_capture_templates = bool(
        invalid_templates and not args.allow_missing_templates and not args.capture_only and not args.list_devices
    )
    if should_auto_capture_templates and args.strict_templates:
        logger.error("Template preflight failed. The following configured template PNG files are missing or invalid:")
        for template_path in invalid_templates:
            logger.error(" - %s", template_path)
        logger.error("Put real cropped PNG template images in templates\\ or run with --allow-missing-templates.")
        pause_on_fatal_exit()
        return 4

    adb_path = resolve_adb_path(args.adb)
    logger.info("Using adb executable: %s", adb_path)
    adb = AdbController(adb_path=adb_path, device_id=args.device)
    matcher = ImageMatcher()
    tesseract_path = resolve_tesseract_path(args.tesseract_cmd)
    if tesseract_path:
        logger.info("Using tesseract executable: %s", tesseract_path)
    matcher.configure_tesseract(tesseract_path)
    action_runner = ActionRunner(adb, SCREENSHOTS_DIR)

    result_log_path, result_log_file, result_writer = open_csv_log()
    logger.info("Result CSV log: %s", result_log_path)

    try:
        if args.list_devices:
            devices = adb.list_device_infos()
            if not devices:
                logger.info("No adb devices found.")
            for device in devices:
                logger.info("ADB device: %s", device.label)
            return 0

        device_id = adb.ensure_device()
        logger.info("Using adb device: %s", device_id)
        logger.info("Device resolution: %sx%s", *adb.get_resolution())

        app_config = config.get("app", {})
        package = app_config.get("package")
        activity = app_config.get("activity")
        if not args.skip_start_app and package:
            try:
                if activity:
                    adb.start_app(package, activity)
                    logger.info("Started app: %s/%s", package, activity)
                else:
                    adb.start_package(package)
                    logger.info("Started app package: %s", package)
            except AdbError as exc:
                logger.error("App launch failed: %s", exc)

        if args.capture_only or should_auto_capture_templates:
            screenshot_prefix = "template_setup" if should_auto_capture_templates else "capture_only"
            screenshot_path = SCREENSHOTS_DIR / f"{screenshot_prefix}_{int(time.time())}.png"
            adb.capture_screen(screenshot_path)
            logger.info("Captured screenshot: %s", screenshot_path)
            if should_auto_capture_templates:
                logger.warning("Configured template PNG files are missing or invalid:")
                for template_path in invalid_templates:
                    logger.warning(" - %s", template_path)
                logger.warning(
                    "Automation did not start because there is nothing valid to match yet. "
                    "Crop the captured screenshot into template PNG files and place them in templates\\."
                )
                logger.warning("Use --allow-missing-templates to force the loop, or --strict-templates to fail fast.")
                pause_on_fatal_exit()
            return 0

        loop_config = config.get("loop", {})
        interval_seconds = float(loop_config.get("interval_seconds", 1))
        max_iterations = int(loop_config.get("max_iterations", 300))
        run_mode = args.run_mode or str(loop_config.get("run_mode", "")).lower().strip()
        if run_mode not in ("scan", "sequence"):
            run_mode = "sequence" if args.script else "scan"
        requested_runs = max(1, int(args.runs))
        monitor_seconds = max(0.0, float(args.monitor_minutes) * 60.0 + float(args.monitor_hours) * 3600.0)
        monitor_deadline = time.time() + monitor_seconds if monitor_seconds > 0 else None
        if args.script:
            logger.info("Selected script: %s (%s scenario(s))", args.script, len(active_config.get("scenarios", [])))
        scenarios = active_config.get("scenarios", [])
        if not scenarios:
            logger.warning("No scenarios configured.")
        logger.info("Run mode: %s", run_mode)
        finish_reason = "requested runs completed"

        run_index = 1
        while True:
            if monitor_deadline and time.time() >= monitor_deadline:
                finish_reason = "monitor duration reached"
                break
            if not monitor_deadline and run_index > requested_runs:
                break

            logger.info("Starting run %s.", run_index)
            run_stopped = False
            next_scenario_index = 0
            for iteration in range(1, max_iterations + 1):
                if monitor_deadline and time.time() >= monitor_deadline:
                    finish_reason = "monitor duration reached"
                    run_stopped = True
                    break

                screenshot_path = SCREENSHOTS_DIR / f"run_{run_index:03d}_screen_{iteration:04d}_{int(time.time())}.png"

                try:
                    adb.capture_screen(screenshot_path)
                    candidate_scenarios = scenarios
                    if run_mode == "sequence":
                        candidate_scenarios = scenarios[next_scenario_index:]
                        if not candidate_scenarios:
                            logger.info("[run %s/%s] Sequence completed.", run_index, iteration)
                            finish_reason = "sequence completed"
                            run_stopped = True
                            break

                    match = matcher.find_first_match(screenshot_path, candidate_scenarios, PROJECT_DIR)

                    if not match:
                        logger.info("[run %s/%s] No scenario matched.", run_index, iteration)
                        write_iteration_log(result_writer, run_index, iteration, screenshot_path, None, None, True, "no match")
                        result_log_file.flush()
                        time.sleep(interval_seconds)
                        continue

                    scenario_name = match.scenario.get("name", "unnamed")
                    if run_mode == "sequence":
                        matched_index = next(
                            (
                                index
                                for index in range(next_scenario_index, len(scenarios))
                                if scenarios[index] is match.scenario
                            ),
                            next_scenario_index,
                        )
                        next_scenario_index = matched_index + 1
                    action = match.scenario.get("action", {"type": "tap"})
                    logger.info(
                        "[run %s/%s] Matched scenario='%s' type=%s score=%.4f center=(%s,%s)",
                        run_index,
                        iteration,
                        scenario_name,
                        match.match_type,
                        match.score,
                        match.center_x,
                        match.center_y,
                    )

                    action_result = action_runner.run(action, match, screenshot_path, iteration)
                    write_iteration_log(
                        result_writer,
                        run_index,
                        iteration,
                        screenshot_path,
                        match,
                        action,
                        True,
                        "action executed",
                        action_result.saved_screenshot_path,
                    )
                    result_log_file.flush()

                    if action_result.should_stop:
                        logger.info("Stop action requested. Ending current run.")
                        run_stopped = True
                        break

                except (AdbError, ValueError, KeyError, OSError) as exc:
                    logger.exception("[run %s/%s] Iteration failed: %s", run_index, iteration, exc)
                    write_iteration_log(result_writer, run_index, iteration, screenshot_path, None, None, False, str(exc))
                    result_log_file.flush()

                time.sleep(interval_seconds)

            logger.info("Run %s finished.", run_index)
            run_index += 1
            if run_stopped and not monitor_deadline:
                if run_index > requested_runs:
                    break
            if monitor_deadline and time.time() < monitor_deadline:
                continue

    except AdbError as exc:
        logger.error("ADB setup failed: %s", exc)
        logger.error(
            "If adb is installed, run with --adb C:\\path\\to\\platform-tools\\adb.exe "
            "or copy platform-tools next to aos_game_auto.exe."
        )
        pause_on_fatal_exit()
        return 3
    finally:
        result_log_file.close()

    report_path = create_markdown_report(
        result_log_path=result_log_path,
        config=config,
        active_config=active_config,
        script_name=args.script,
        started_at=started_at,
        finished_at=datetime.now(),
        finish_reason=finish_reason,
    )
    logger.info("Report written: %s", report_path)
    logger.info("Automation finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
