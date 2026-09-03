from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from app.core.errors import DomainError
from app.schemas.test_cases import ImportedTestCase, ImportedTestCaseItem


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_XML_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 50_000
ALLOWED_EXTENSIONS = {".txt", ".csv", ".xlsx", ".docx"}


def _clean(lines: list[str]) -> str:
    text = "\n".join(line.strip() for line in lines if line and line.strip()).strip()
    if not text:
        raise DomainError("EMPTY_TEST_CASE_FILE", "파일에서 테스트 케이스 내용을 찾지 못했습니다.", 422)
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise DomainError(
            "EXTRACTED_TEXT_TOO_LARGE",
            "추출된 테스트 케이스 내용이 50,000자를 초과합니다.",
            413,
            details={"maxCharacters": MAX_EXTRACTED_CHARACTERS},
        )
    return text


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DomainError("UNSUPPORTED_TEXT_ENCODING", "텍스트 파일은 UTF-8 또는 CP949 인코딩이어야 합니다.", 422)


def _parse_csv(data: bytes) -> str:
    decoded = _decode_text(data)
    rows = csv.reader(io.StringIO(decoded))
    return _clean([" | ".join(cell.strip() for cell in row if cell.strip()) for row in rows])


def _read_archive_member(archive: ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MAX_ARCHIVE_XML_BYTES:
        raise DomainError("INVALID_DOCUMENT", "문서 내부 데이터가 허용 크기를 초과합니다.", 422)
    return archive.read(info)


def _parse_docx(data: bytes) -> str:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(io.BytesIO(data)) as archive:
        xml = _read_archive_member(archive, "word/document.xml")
    root = ElementTree.fromstring(xml)
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        paragraphs.append("".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)))
    return _clean(paragraphs)


def _normalize_header(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum() or "가" <= character <= "힣")


def _is_tc_header(row: list[str]) -> bool:
    headers = {_normalize_header(value) for value in row}
    id_headers = {"id", "tcid", "tcno", "testcaseid", "testcaseno", "테스트케이스id", "케이스id"}
    step_headers = {"step", "steps", "teststep", "teststeps", "단계", "테스트단계"}
    expected_headers = {"expectedresult", "expected", "기대결과", "예상결과"}
    return bool(headers & expected_headers) and bool(headers & (id_headers | step_headers))


def _looks_like_tc_id(value: str) -> bool:
    return bool(re.fullmatch(r"(?i)(?=.*\d)[a-z0-9]+(?:[-_][a-z0-9]+)+", value.strip()))


def _has_nearby_value(row: list[str], columns: list[int]) -> bool:
    candidates = {index + offset for index in columns for offset in (-1, 0, 1) if index + offset >= 0}
    ignored = {"pass", "fail", "na", "block", "blocked", "nottest", "미실행"}
    return any(
        index < len(row)
        and row[index].strip()
        and _normalize_header(row[index]) not in ignored
        and not row[index].strip().lower().startswith(("source:", "source："))
        for index in candidates
    )


def _is_xlsx_non_tc_row(row: list[str], step_columns: list[int], expected_columns: list[int]) -> bool:
    values = [value.strip() for value in row if value and value.strip()]
    if not values or _is_tc_header(values):
        return True
    if len(values) == 1 and re.fullmatch(r"\d+[.)]?", values[0]):
        return True
    normalized = [_normalize_header(value) for value in values]
    metadata_labels = {"담당자", "브라우저", "buildversion", "빌드버전", "확인일", "작성일"}
    if normalized[0] in metadata_labels and len(values) <= 3:
        return True
    has_tc_id = any(_looks_like_tc_id(value) for value in values)
    has_step_and_expected = _has_nearby_value(row, step_columns) and _has_nearby_value(row, expected_columns)
    if has_tc_id or has_step_and_expected:
        return False
    statuses = {"pass", "fail", "na", "block", "blocked", "nottest", "미실행"}
    has_status = any(value in statuses for value in normalized)
    has_source = any(value.lower().startswith("source:") or value.lower().startswith("source：") for value in values)
    return has_status and has_source


def _header_index(headers: list[str], aliases: set[str]) -> int | None:
    return next((index for index, value in enumerate(headers) if value in aliases), None)


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


def _split_lines(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\r\n]+", value) if part.strip()]


def _item_raw_text(item: dict) -> str:
    lines = []
    if item.get("externalId"):
        lines.append(f"TC ID: {item['externalId']}")
    if item.get("title"):
        lines.append(f"제목: {item['title']}")
    if item.get("precondition"):
        lines.append(f"전제조건: {item['precondition']}")
    lines.extend(f"단계 {index}: {step}" for index, step in enumerate(item.get("steps") or [], start=1))
    if item.get("expected"):
        lines.append(f"기대결과: {item['expected']}")
    if item.get("sourceUrl"):
        lines.append(f"대상 URL: {item['sourceUrl']}")
    return "\n".join(lines)


def _parse_tc_items(header: list[str], content_rows: list[list[str]]) -> list[ImportedTestCaseItem]:
    headers = [_normalize_header(value) for value in header]
    indices = {
        "id": _header_index(headers, {"id", "tcid", "tcno", "testcaseid", "testcaseno", "테스트케이스id", "케이스id"}),
        "depth1": _header_index(headers, {"depth1", "대분류", "1depth"}),
        "depth2": _header_index(headers, {"depth2", "중분류", "2depth"}),
        "depth3": _header_index(headers, {"depth3", "소분류", "3depth"}),
        "precondition": _header_index(headers, {"precondition", "preconditions", "사전조건", "전제조건"}),
        "steps": _header_index(headers, {"step", "steps", "teststep", "teststeps", "단계", "테스트단계"}),
        "expected": _header_index(headers, {"expectedresult", "expected", "기대결과", "예상결과"}),
    }
    audit_indices = {
        header[index]: index for index, normalized in enumerate(headers)
        if normalized in {"resultaos", "resultios", "result", "btsid", "comment", "비고", "결과"}
    }
    items: list[dict] = []
    current: dict | None = None
    for row in content_rows:
        external_id = _cell(row, indices["id"])
        if not _looks_like_tc_id(external_id):
            external_id = next((value.strip() for value in row if _looks_like_tc_id(value)), "")
        starts_item = bool(external_id and _looks_like_tc_id(external_id))
        if starts_item or current is None:
            depth = [_cell(row, indices[key]) for key in ("depth1", "depth2", "depth3")]
            title = " > ".join(value for value in depth if value) or external_id or "가져온 테스트 케이스"
            current = {
                "externalId": external_id or None, "title": title,
                "depth1": depth[0] or None, "depth2": depth[1] or None, "depth3": depth[2] or None,
                "precondition": _cell(row, indices["precondition"]) or None,
                "steps": _split_lines(_cell(row, indices["steps"])),
                "expectedParts": _split_lines(_cell(row, indices["expected"])),
                "auditFields": {name: _cell(row, index) for name, index in audit_indices.items() if _cell(row, index)},
            }
            items.append(current)
        else:
            current["steps"].extend(_split_lines(_cell(row, indices["steps"])))
            current["expectedParts"].extend(_split_lines(_cell(row, indices["expected"])))
            for name, index in audit_indices.items():
                value = _cell(row, index)
                if value:
                    current["auditFields"][name] = "\n".join(filter(None, [current["auditFields"].get(name), value]))
        comment_text = "\n".join(current["auditFields"].values())
        source_match = re.search(r"https?://[^\s|)]+", comment_text)
        current["sourceUrl"] = source_match.group(0).rstrip(".,") if source_match else current.get("sourceUrl")
    results = []
    for item in items:
        item["expected"] = "\n".join(dict.fromkeys(item.pop("expectedParts"))) or None
        item["steps"] = list(dict.fromkeys(item["steps"]))
        raw_text = _item_raw_text(item)
        if raw_text:
            results.append(ImportedTestCaseItem(**item, rawText=raw_text))
    return results


def _prepare_xlsx_rows(rows: list[list[str]]) -> tuple[str, list[str], list[ImportedTestCaseItem]]:
    header_index = next((index for index, row in enumerate(rows) if _is_tc_header(row)), None)
    if header_index is None:
        return _clean([" | ".join(value for value in row if value) for row in rows]), [], []
    tc_rows = rows[header_index:]
    normalized_header = [_normalize_header(value) for value in tc_rows[0]]
    step_headers = {"step", "steps", "teststep", "teststeps", "단계", "테스트단계"}
    expected_headers = {"expectedresult", "expected", "기대결과", "예상결과"}
    step_columns = [index for index, value in enumerate(normalized_header) if value in step_headers]
    expected_columns = [index for index, value in enumerate(normalized_header) if value in expected_headers]
    content_rows = [row for row in tc_rows[1:] if not _is_xlsx_non_tc_row(row, step_columns, expected_columns)]
    detected_ids = {value.strip().lower() for row in content_rows for value in row if _looks_like_tc_id(value)}
    detected_count = len(detected_ids) if detected_ids else len(content_rows)
    warnings = [
        f"XLSX_METADATA_ROWS_EXCLUDED:{header_index}",
        f"XLSX_TEST_CASES_DETECTED:{detected_count}",
    ]
    excluded_content_count = len(tc_rows) - 1 - len(content_rows)
    if excluded_content_count:
        warnings.append(f"XLSX_NON_TC_ROWS_EXCLUDED:{excluded_content_count}")
    items = _parse_tc_items(tc_rows[0], content_rows)
    safe_raw_text = _clean([item.rawText for item in items]) if items else _clean([" | ".join(value for value in row if value) for row in content_rows])
    return safe_raw_text, warnings, items


def _xlsx_column_index(reference: str) -> int:
    letters = "".join(character for character in reference.upper() if character.isalpha())
    value = 0
    for character in letters:
        value = value * 26 + ord(character) - ord("A") + 1
    return max(0, value - 1)


def _parse_xlsx(data: bytes) -> tuple[str, list[str], list[ImportedTestCaseItem]]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    doc_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(_read_archive_member(archive, "xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter(f"{{{main_ns}}}t")) for item in root]

        workbook = ElementTree.fromstring(_read_archive_member(archive, "xl/workbook.xml"))
        relationships = ElementTree.fromstring(_read_archive_member(archive, "xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships.findall(f"{{{rel_ns}}}Relationship")}
        rows: list[list[str]] = []
        for sheet in workbook.findall(f".//{{{main_ns}}}sheet"):
            relationship_id = sheet.attrib[f"{{{doc_rel_ns}}}id"]
            target = targets[relationship_id].lstrip("/")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            sheet_root = ElementTree.fromstring(_read_archive_member(archive, sheet_path))
            for row in sheet_root.findall(f".//{{{main_ns}}}row"):
                values: list[str] = []
                for cell in row.findall(f"{{{main_ns}}}c"):
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find(f"{{{main_ns}}}v")
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(f"{{{main_ns}}}t"))
                    elif value_node is None:
                        value = ""
                    elif cell_type == "s":
                        value = shared[int(value_node.text or "0")]
                    else:
                        value = value_node.text or ""
                    column_index = _xlsx_column_index(cell.attrib.get("r", "")) if cell.attrib.get("r") else len(values)
                    if len(values) <= column_index:
                        values.extend([""] * (column_index + 1 - len(values)))
                    values[column_index] = value.strip()
                if any(values):
                    rows.append(values)
    return _prepare_xlsx_rows(rows)


def import_test_case(filename: str, data: bytes) -> ImportedTestCase:
    safe_name = Path(filename or "upload").name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise DomainError(
            "UNSUPPORTED_FILE_TYPE",
            "TXT, CSV, XLSX, DOCX 파일만 업로드할 수 있습니다.",
            415,
            details={"allowedExtensions": sorted(ALLOWED_EXTENSIONS)},
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise DomainError("FILE_TOO_LARGE", "파일 크기는 10MB 이하여야 합니다.", 413, details={"maxBytes": MAX_UPLOAD_BYTES})
    if not data:
        raise DomainError("EMPTY_TEST_CASE_FILE", "빈 파일은 업로드할 수 없습니다.", 422)

    try:
        if extension == ".txt":
            raw_text = _clean(_decode_text(data).splitlines())
        elif extension == ".csv":
            raw_text = _parse_csv(data)
        elif extension == ".docx":
            raw_text = _parse_docx(data)
        else:
            raw_text, warnings, test_cases = _parse_xlsx(data)
    except (BadZipFile, KeyError, ElementTree.ParseError, IndexError, ValueError):
        raise DomainError("INVALID_DOCUMENT", "손상되었거나 지원하지 않는 문서 구조입니다.", 422) from None

    return ImportedTestCase(
        fileName=safe_name,
        format=extension.removeprefix("."),
        title=Path(safe_name).stem[:200] or "가져온 테스트 케이스",
        rawText=raw_text,
        warnings=warnings if extension == ".xlsx" else [],
        detectedTestCaseCount=len(test_cases) if extension == ".xlsx" else 0,
        testCases=test_cases if extension == ".xlsx" else [],
    )
