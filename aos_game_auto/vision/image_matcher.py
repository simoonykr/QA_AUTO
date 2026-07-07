import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import cv2

try:
    import pytesseract
except ImportError:  # Optional OCR dependency.
    pytesseract = None


@dataclass
class MatchResult:
    scenario: Dict[str, Any]
    template_path: Path
    score: float
    center_x: int
    center_y: int
    top_left_x: int
    top_left_y: int
    match_type: str = "template"
    matched_text: str = ""


class ImageMatcher:
    """Finds template or OCR text matches in screenshots."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def configure_tesseract(self, command_path: Optional[str]) -> None:
        if command_path and pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = command_path

    def find_template(
        self,
        screenshot_path: Path,
        template_path: Path,
        threshold: float,
        screenshot_image: Any = None,
    ) -> Optional[MatchResult]:
        screenshot = screenshot_image
        if screenshot is None:
            screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if screenshot is None:
            raise ValueError(f"Could not read screenshot: {screenshot_path}")

        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if template is None:
            self.logger.warning("Template image could not be read: %s", template_path)
            return None

        if template.shape[0] > screenshot.shape[0] or template.shape[1] > screenshot.shape[1]:
            self.logger.warning("Template is larger than screenshot: %s", template_path)
            return None

        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_location = cv2.minMaxLoc(result)

        if max_value < threshold:
            return None

        template_height, template_width = template.shape[:2]
        top_left_x, top_left_y = max_location
        return MatchResult(
            scenario={},
            template_path=template_path,
            score=float(max_value),
            center_x=int(top_left_x + template_width / 2),
            center_y=int(top_left_y + template_height / 2),
            top_left_x=int(top_left_x),
            top_left_y=int(top_left_y),
        )

    def find_first_match(self, screenshot_path: Path, scenarios: Iterable[Dict[str, Any]], base_dir: Path) -> Optional[MatchResult]:
        screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if screenshot is None:
            raise ValueError(f"Could not read screenshot: {screenshot_path}")

        for scenario in scenarios:
            match_configs = self._scenario_match_configs(scenario)
            if not match_configs:
                self.logger.warning("Scenario '%s' has no match configuration.", scenario.get("name", "unnamed"))
                continue

            best_match: Optional[MatchResult] = None
            for match_config in match_configs:
                match_type = str(match_config.get("type", "template")).lower()
                if match_type == "ocr":
                    match = self.find_ocr_text(screenshot_path, screenshot, match_config)
                else:
                    match = self._find_best_template_match(screenshot_path, screenshot, match_config, base_dir)
                if match and (best_match is None or match.score > best_match.score):
                    best_match = match

            if best_match:
                best_match.scenario = scenario
                return best_match

        return None

    def _find_best_template_match(
        self,
        screenshot_path: Path,
        screenshot: Any,
        match_config: Dict[str, Any],
        base_dir: Path,
    ) -> Optional[MatchResult]:
        template_values = self._template_values_from_config(match_config)
        if not template_values:
            return None

        threshold = float(match_config.get("threshold", 0.85))
        best_match: Optional[MatchResult] = None
        for template_value in template_values:
            template_path = Path(template_value)
            if not template_path.is_absolute():
                template_path = base_dir / template_path

            match = self.find_template(screenshot_path, template_path, threshold, screenshot_image=screenshot)
            if match and (best_match is None or match.score > best_match.score):
                best_match = match
        return best_match

    def find_ocr_text(self, screenshot_path: Path, screenshot: Any, match_config: Dict[str, Any]) -> Optional[MatchResult]:
        if pytesseract is None:
            self.logger.warning("OCR scenario configured but pytesseract is not installed.")
            return None

        target = str(match_config.get("text", "")).strip()
        if not target:
            self.logger.warning("OCR scenario has no target text.")
            return None

        threshold = float(match_config.get("threshold", 0.6))
        lang = str(match_config.get("lang", "kor+eng"))
        contains = bool(match_config.get("contains", True))
        x_offset, y_offset, roi = self._crop_search_area(screenshot, match_config.get("search_area"))

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 5, 50, 50)
        try:
            data = pytesseract.image_to_data(gray, lang=lang, output_type=pytesseract.Output.DICT)
        except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
            self.logger.warning("OCR failed: %s", exc)
            return None

        best: Optional[tuple[float, str, tuple[int, int, int, int]]] = None
        line_groups: dict[tuple[int, int, int], list[int]] = {}
        for index, text in enumerate(data.get("text", [])):
            if str(text).strip():
                key = (
                    int(data["block_num"][index]),
                    int(data["par_num"][index]),
                    int(data["line_num"][index]),
                )
                line_groups.setdefault(key, []).append(index)

        for indexes in line_groups.values():
            texts = [str(data["text"][index]).strip() for index in indexes if str(data["text"][index]).strip()]
            if not texts:
                continue
            line_text = " ".join(texts)
            normalized_line = self._normalize_text(line_text)
            normalized_target = self._normalize_text(target)
            is_match = normalized_target in normalized_line if contains else normalized_target == normalized_line
            if not is_match:
                continue

            confidences = []
            lefts, tops, rights, bottoms = [], [], [], []
            for index in indexes:
                try:
                    conf = float(data["conf"][index])
                except (ValueError, TypeError):
                    conf = -1
                if conf >= 0:
                    confidences.append(conf)
                left = int(data["left"][index])
                top = int(data["top"][index])
                width = int(data["width"][index])
                height = int(data["height"][index])
                lefts.append(left)
                tops.append(top)
                rights.append(left + width)
                bottoms.append(top + height)

            score = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
            if score < threshold:
                continue
            bbox = (min(lefts), min(tops), max(rights), max(bottoms))
            if best is None or score > best[0]:
                best = (score, line_text, bbox)

        if best is None:
            return None

        score, matched_text, (left, top, right, bottom) = best
        absolute_left = x_offset + left
        absolute_top = y_offset + top
        absolute_right = x_offset + right
        absolute_bottom = y_offset + bottom
        return MatchResult(
            scenario={},
            template_path=Path(f"ocr:{target}"),
            score=float(score),
            center_x=int((absolute_left + absolute_right) / 2),
            center_y=int((absolute_top + absolute_bottom) / 2),
            top_left_x=int(absolute_left),
            top_left_y=int(absolute_top),
            match_type="ocr",
            matched_text=matched_text,
        )

    def _crop_search_area(self, image: Any, search_area: Any) -> tuple[int, int, Any]:
        if not isinstance(search_area, dict):
            return 0, 0, image
        height, width = image.shape[:2]
        x = max(0, min(int(search_area.get("x", 0)), width - 1))
        y = max(0, min(int(search_area.get("y", 0)), height - 1))
        w = max(1, int(search_area.get("w", width - x)))
        h = max(1, int(search_area.get("h", height - y)))
        right = max(x + 1, min(x + w, width))
        bottom = max(y + 1, min(y + h, height))
        return x, y, image[y:bottom, x:right]

    def _normalize_text(self, text: str) -> str:
        return "".join(str(text).lower().split())

    def _scenario_match_configs(self, scenario: Dict[str, Any]) -> list[Dict[str, Any]]:
        match_any = scenario.get("match_any")
        if isinstance(match_any, list):
            return [value for value in match_any if isinstance(value, dict)]

        match_value = scenario.get("match")
        if isinstance(match_value, dict):
            return [match_value]

        if scenario.get("ocr_text"):
            return [
                {
                    "type": "ocr",
                    "text": scenario.get("ocr_text"),
                    "threshold": scenario.get("ocr_threshold", scenario.get("threshold", 0.6)),
                    "lang": scenario.get("ocr_lang", "kor+eng"),
                    "search_area": scenario.get("search_area"),
                }
            ]

        template_values = self._scenario_template_values(scenario)
        if template_values:
            return [
                {
                    "type": "template",
                    "template": scenario.get("template"),
                    "templates": scenario.get("templates"),
                    "threshold": scenario.get("threshold", 0.85),
                }
            ]
        return []

    def _template_values_from_config(self, match_config: Dict[str, Any]) -> list[str]:
        values: list[str] = []
        templates_value = match_config.get("templates")
        if isinstance(templates_value, list):
            values.extend(str(value) for value in templates_value if value)

        template_value = match_config.get("template")
        if template_value:
            template_text = str(template_value)
            if template_text not in values:
                values.append(template_text)
        return values

    def _scenario_template_values(self, scenario: Dict[str, Any]) -> list[str]:
        values: list[str] = []
        templates_value = scenario.get("templates")
        if isinstance(templates_value, list):
            values.extend(str(value) for value in templates_value if value)

        template_value = scenario.get("template")
        if template_value:
            template_text = str(template_value)
            if template_text not in values:
                values.append(template_text)
        return values
