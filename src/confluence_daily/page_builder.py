from __future__ import annotations

from datetime import date
import html
import xml.etree.ElementTree as ET

from .calendar_utils import (
    format_date_label,
    row_index_for_date,
    week_number_for_date,
    weeks_in_month,
)
from .models import ConflictPolicy, DailyEntryConflict, UploadedAttachment


AC_NS = "http://atlassian.com/content"
RI_NS = "http://atlassian.com/resource/identifier"

LABEL_DATE = "\ub0a0\uc9dc"
LABEL_WORK = "\uc5c5\ubb34 \ub0b4\uc6a9"
LABEL_NOTE = "\ucc38\uace0"

ET.register_namespace("ac", AC_NS)
ET.register_namespace("ri", RI_NS)


def _q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def _ac_attr(name: str) -> str:
    return _q(AC_NS, name)


def _ri_attr(name: str) -> str:
    return _q(RI_NS, name)


def build_month_storage(year: int, month: int, minimum_weeks: int = 4) -> str:
    root = ET.Element("root")
    for week in range(1, weeks_in_month(year, month, minimum_weeks) + 1):
        root.append(_build_week_macro(week))
    return _serialize_root(root)


def has_daily_conflict(storage: str, work_date: date) -> bool:
    return has_daily_conflict_for_month(storage, work_date, work_date.year, work_date.month)


def has_daily_conflict_for_month(storage: str, work_date: date, target_year: int, target_month: int) -> bool:
    root = _parse_storage(storage)
    week = week_number_for_date(work_date, target_year, target_month)
    macro = _find_week_macro(root, week)
    if macro is None:
        return False

    table = _find_first_table(macro)
    if table is None:
        return False

    rows = _table_rows(table)
    if len(rows) < 2 + row_index_for_date(work_date):
        return False

    cells = _row_cells(rows[1 + row_index_for_date(work_date)])
    if len(cells) < 3:
        return False
    return _cell_has_content(cells[1]) or _cell_has_content(cells[2])


def update_storage_for_entry(
    storage: str,
    work_date: date,
    attachments: tuple[UploadedAttachment, ...],
    comment: str,
    conflict_policy: ConflictPolicy = "cancel",
    minimum_weeks: int = 4,
) -> str:
    return update_storage_for_entry_for_month(
        storage,
        work_date,
        attachments,
        comment,
        work_date.year,
        work_date.month,
        conflict_policy,
        minimum_weeks,
    )


def update_storage_for_entry_for_month(
    storage: str,
    work_date: date,
    attachments: tuple[UploadedAttachment, ...],
    comment: str,
    target_year: int,
    target_month: int,
    conflict_policy: ConflictPolicy = "cancel",
    minimum_weeks: int = 4,
) -> str:
    root = _parse_storage(storage)
    required_weeks = max(minimum_weeks, weeks_in_month(target_year, target_month))
    _ensure_week_sections(root, required_weeks)

    week = week_number_for_date(work_date, target_year, target_month)
    row_index = row_index_for_date(work_date)
    macro = _find_week_macro(root, week)
    if macro is None:
        raise RuntimeError(f"Failed to create {week}\uc8fc\ucc28 section.")

    table = _find_or_create_table(macro)
    _ensure_table_shape(table)
    target_row = _table_rows(table)[1 + row_index]
    date_cell, work_cell, comment_cell = _row_cells(target_row)[:3]

    conflict = _cell_has_content(work_cell) or _cell_has_content(comment_cell)
    if conflict and conflict_policy == "cancel":
        raise DailyEntryConflict(f"{format_date_label(work_date)} row already has content.")

    _replace_cell(date_cell, _date_elements(work_date))
    work_elements = _attachment_elements(attachments)
    comment_elements = _comment_elements(comment)

    if conflict and conflict_policy == "append":
        _append_to_cell(work_cell, work_elements)
        _append_to_cell(comment_cell, comment_elements)
    else:
        _replace_cell(work_cell, work_elements)
        _replace_cell(comment_cell, comment_elements)

    return _serialize_root(root)


def _parse_storage(storage: str) -> ET.Element:
    cleaned = storage.replace("&nbsp;", "&#160;")
    wrapped = (
        f'<root xmlns:ac="{AC_NS}" xmlns:ri="{RI_NS}">'
        f"{cleaned}"
        "</root>"
    )
    try:
        return ET.fromstring(wrapped)
    except ET.ParseError as exc:
        raise ValueError(f"Confluence storage body is not valid XML/XHTML: {exc}") from exc


def _serialize_root(root: ET.Element) -> str:
    parts: list[str] = []
    if root.text and root.text.strip():
        parts.append(html.escape(root.text))
    for child in list(root):
        parts.append(ET.tostring(child, encoding="unicode", short_empty_elements=True))
        if child.tail and child.tail.strip():
            parts.append(html.escape(child.tail))
    return "\n".join(parts)


def _build_week_macro(week: int) -> ET.Element:
    macro = ET.Element(
        _q(AC_NS, "structured-macro"),
        {
            _ac_attr("name"): "expand",
            _ac_attr("schema-version"): "1",
        },
    )
    title = ET.SubElement(macro, _q(AC_NS, "parameter"), {_ac_attr("name"): "title"})
    title.text = f"{week}\uc8fc\ucc28"
    body = ET.SubElement(macro, _q(AC_NS, "rich-text-body"))
    body.append(_build_daily_table())
    return macro


def _build_daily_table() -> ET.Element:
    table = ET.Element("table", {"class": "wrapped"})
    colgroup = ET.SubElement(table, "colgroup")
    for _ in range(3):
        ET.SubElement(colgroup, "col")
    tbody = ET.SubElement(table, "tbody")

    header = ET.SubElement(tbody, "tr")
    for label in (LABEL_DATE, LABEL_WORK, LABEL_NOTE):
        th = ET.SubElement(header, "th")
        th.text = label

    for _ in range(5):
        row = ET.SubElement(tbody, "tr")
        for _ in range(3):
            td = ET.SubElement(row, "td")
            td.append(_br())
    return table


def _find_week_macro(root: ET.Element, week: int) -> ET.Element | None:
    target_title = f"{week}\uc8fc\ucc28"
    for macro in root.iter(_q(AC_NS, "structured-macro")):
        if macro.attrib.get(_ac_attr("name")) != "expand":
            continue
        for param in macro.findall(_q(AC_NS, "parameter")):
            if param.attrib.get(_ac_attr("name")) == "title" and (param.text or "").strip() == target_title:
                return macro
    return None


def _ensure_week_sections(root: ET.Element, required_weeks: int) -> None:
    for week in range(1, required_weeks + 1):
        if _find_week_macro(root, week) is None:
            root.append(_build_week_macro(week))


def _find_first_table(parent: ET.Element) -> ET.Element | None:
    for element in parent.iter("table"):
        return element
    return None


def _find_or_create_table(macro: ET.Element) -> ET.Element:
    table = _find_first_table(macro)
    if table is not None:
        return table

    body = macro.find(_q(AC_NS, "rich-text-body"))
    if body is None:
        body = ET.SubElement(macro, _q(AC_NS, "rich-text-body"))
    table = _build_daily_table()
    body.append(table)
    return table


def _ensure_table_shape(table: ET.Element) -> None:
    _ensure_colgroup(table)
    tbody = _table_body(table)
    rows = list(tbody.findall("./tr"))
    if not rows:
        header = ET.SubElement(tbody, "tr")
        for label in (LABEL_DATE, LABEL_WORK, LABEL_NOTE):
            th = ET.SubElement(header, "th")
            th.text = label
        rows = [header]

    while len(rows) < 6:
        row = ET.SubElement(tbody, "tr")
        rows.append(row)

    for row_index, row in enumerate(rows[:6]):
        cells = _row_cells(row)
        while len(cells) < 3:
            cell = ET.SubElement(row, "th" if row_index == 0 else "td")
            if row_index == 0:
                cell.text = (LABEL_DATE, LABEL_WORK, LABEL_NOTE)[len(cells)]
            else:
                cell.append(_br())
            cells.append(cell)


def _ensure_colgroup(table: ET.Element) -> None:
    if table.find("./colgroup") is not None:
        return
    colgroup = ET.Element("colgroup")
    for _ in range(3):
        ET.SubElement(colgroup, "col")
    table.insert(0, colgroup)


def _table_body(table: ET.Element) -> ET.Element:
    tbody = table.find("./tbody")
    if tbody is not None:
        return tbody

    tbody = ET.Element("tbody")
    direct_rows = list(table.findall("./tr"))
    for row in direct_rows:
        table.remove(row)
        tbody.append(row)
    table.append(tbody)
    return tbody


def _table_rows(table: ET.Element) -> list[ET.Element]:
    return list(_table_body(table).findall("./tr"))


def _row_cells(row: ET.Element) -> list[ET.Element]:
    return [child for child in list(row) if child.tag in {"td", "th"}]


def _paragraph(text: str | None = None) -> ET.Element:
    paragraph = ET.Element("p")
    if text:
        paragraph.text = text
    return paragraph


def _br() -> ET.Element:
    return ET.Element("br")


def _content_wrapper(children: list[ET.Element]) -> ET.Element:
    wrapper = ET.Element("div", {"class": "content-wrapper"})
    paragraph = ET.SubElement(wrapper, "p")
    for child in children:
        paragraph.append(child)
    if not children:
        paragraph.append(_br())
    return wrapper


def _date_elements(work_date: date) -> list[ET.Element]:
    time_node = ET.Element("time", {"datetime": work_date.isoformat()})
    time_node.tail = "\xa0"
    return [_content_wrapper([time_node])]


def _comment_elements(comment: str) -> list[ET.Element]:
    lines = comment.splitlines()
    if not lines:
        return [_br()]
    if len(lines) == 1:
        paragraph = _paragraph(lines[0])
        return [paragraph]
    return [_paragraph(line) for line in lines]


def _attachment_elements(attachments: tuple[UploadedAttachment, ...]) -> list[ET.Element]:
    if not attachments:
        return [_br()]

    media_nodes: list[ET.Element] = []
    for attachment in attachments:
        if attachment.media_kind == "image":
            media_nodes.append(_image_node(attachment.attachment_name))
        elif attachment.media_kind == "video":
            media_nodes.append(_view_file_node(attachment.attachment_name))
        else:
            media_nodes.append(_attachment_link_node(attachment.attachment_name))
    return [_content_wrapper(media_nodes)]


def _image_node(filename: str) -> ET.Element:
    image = ET.Element(
        _q(AC_NS, "image"),
        {
            _ac_attr("thumbnail"): "true",
            _ac_attr("height"): "250",
        },
    )
    ET.SubElement(image, _q(RI_NS, "attachment"), {_ri_attr("filename"): filename})
    return image


def _view_file_node(filename: str) -> ET.Element:
    macro = ET.Element(
        _q(AC_NS, "structured-macro"),
        {
            _ac_attr("name"): "view-file",
            _ac_attr("schema-version"): "1",
        },
    )
    name = ET.SubElement(macro, _q(AC_NS, "parameter"), {_ac_attr("name"): "name"})
    ET.SubElement(name, _q(RI_NS, "attachment"), {_ri_attr("filename"): filename})
    height = ET.SubElement(macro, _q(AC_NS, "parameter"), {_ac_attr("name"): "height"})
    height.text = "250"
    return macro


def _attachment_link_node(filename: str) -> ET.Element:
    link = ET.Element(_q(AC_NS, "link"))
    ET.SubElement(link, _q(RI_NS, "attachment"), {_ri_attr("filename"): filename})
    body = ET.SubElement(link, _q(AC_NS, "plain-text-link-body"))
    body.text = filename
    return link


def _replace_cell(cell: ET.Element, elements: list[ET.Element]) -> None:
    cell.text = None
    for child in list(cell):
        cell.remove(child)
    for element in elements:
        cell.append(element)


def _append_to_cell(cell: ET.Element, elements: list[ET.Element]) -> None:
    if _cell_has_content(cell):
        separator = ET.Element("p")
        separator.text = "---"
        cell.append(separator)
    for element in elements:
        cell.append(element)


def _cell_has_content(cell: ET.Element) -> bool:
    for text in cell.itertext():
        if text.replace("\xa0", "").strip():
            return True

    for node in cell.iter():
        if node is cell:
            continue
        local = _local_name(node.tag)
        if local in {"image", "link", "attachment", "structured-macro"}:
            return True
    return False


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag
