from __future__ import annotations

import csv
import io
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from app.core.errors import DomainError
from app.schemas.test_cases import ImportedTestCase


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
    id_headers = {"tcid", "tcno", "testcaseid", "testcaseno", "테스트케이스id", "케이스id"}
    step_headers = {"step", "steps", "teststep", "teststeps", "단계", "테스트단계"}
    expected_headers = {"expectedresult", "expected", "기대결과", "예상결과"}
    return bool(headers & expected_headers) and bool(headers & (id_headers | step_headers))


def _prepare_xlsx_rows(rows: list[list[str]]) -> tuple[str, list[str]]:
    header_index = next((index for index, row in enumerate(rows) if _is_tc_header(row)), None)
    if header_index is None:
        return _clean([" | ".join(value for value in row if value) for row in rows]), []
    tc_rows = rows[header_index:]
    normalized_header = [_normalize_header(value) for value in tc_rows[0]]
    id_headers = {"tcid", "tcno", "testcaseid", "testcaseno", "테스트케이스id", "케이스id"}
    id_column = next((index for index, value in enumerate(normalized_header) if value in id_headers), None)
    if id_column is None:
        detected_count = sum(1 for row in tc_rows[1:] if any(value.strip() for value in row))
    else:
        detected_count = sum(1 for row in tc_rows[1:] if len(row) > id_column and row[id_column].strip())
    warnings = [
        f"XLSX_METADATA_ROWS_EXCLUDED:{header_index}",
        f"XLSX_TEST_CASES_DETECTED:{detected_count}",
    ]
    return _clean([" | ".join(value for value in row if value) for row in tc_rows]), warnings


def _parse_xlsx(data: bytes) -> tuple[str, list[str]]:
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
                    values.append(value.strip())
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
            raw_text, warnings = _parse_xlsx(data)
    except (BadZipFile, KeyError, ElementTree.ParseError, IndexError, ValueError):
        raise DomainError("INVALID_DOCUMENT", "손상되었거나 지원하지 않는 문서 구조입니다.", 422) from None

    return ImportedTestCase(
        fileName=safe_name,
        format=extension.removeprefix("."),
        title=Path(safe_name).stem[:200] or "가져온 테스트 케이스",
        rawText=raw_text,
        warnings=warnings if extension == ".xlsx" else [],
    )
