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


def _parse_xlsx(data: bytes) -> str:
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
        lines: list[str] = []
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
                    if value.strip():
                        values.append(value.strip())
                if values:
                    lines.append(" | ".join(values))
    return _clean(lines)


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
            raw_text = _parse_xlsx(data)
    except (BadZipFile, KeyError, ElementTree.ParseError, IndexError, ValueError):
        raise DomainError("INVALID_DOCUMENT", "손상되었거나 지원하지 않는 문서 구조입니다.", 422) from None

    return ImportedTestCase(
        fileName=safe_name,
        format=extension.removeprefix("."),
        title=Path(safe_name).stem[:200] or "가져온 테스트 케이스",
        rawText=raw_text,
    )
