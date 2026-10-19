"""EML entity references.

Build step 3 needs only what both backends use to list a package's data
entities: each entity's name, type, object name, distribution URL and its
PASTA entity id. PASTA names a data entity by the MD5 of its ``entityName``
(verified 2026-10-17 on knb-lter-hbr.14.22), so the id is known even when the
distribution URL is not a PASTA URL. The full metadata projection lives in
:mod:`edi_mcp.projections.eml`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from edi_mcp.edi.xml import child, children, descendants, parse_xml, text_of

ENTITY_TYPES = (
    "dataTable",
    "spatialRaster",
    "spatialVector",
    "storedProcedure",
    "view",
    "otherEntity",
)
_PASTA_ENTITY_RE = re.compile(r"/package/data/eml/[^/]+/\d+/\d+/(?P<entity>[0-9a-f]{32})$")


@dataclass(frozen=True)
class EmlEntity:
    name: str | None
    entity_type: str
    object_name: str | None
    url: str | None
    entity_id: str | None
    size: int | None
    format: str | None


def pasta_entity_id(entity_name: str) -> str:
    """PASTA's data entity id: the MD5 hex digest of the EML ``entityName``."""
    return hashlib.md5(entity_name.encode("utf-8"), usedforsecurity=False).hexdigest()


_BYTE_UNITS = ("", "byte", "bytes")


def size_bytes(element: Element | None) -> int | None:
    """``physical/size`` in bytes; ``None`` for another ``unit`` (kilobyte, …) or junk."""
    if element is None or element.text is None:
        return None
    if (element.get("unit") or "").strip().lower() not in _BYTE_UNITS:
        return None
    try:
        return int(float(element.text.strip()))
    except ValueError:
        return None


def entity_refs(
    eml: bytes | str | Element, *, source: str, service: str = "PASTA"
) -> list[EmlEntity]:
    """Every data entity declared in ``eml`` (bytes or an already parsed root), in order."""
    root = eml if isinstance(eml, Element) else parse_xml(eml, source=source, service=service)
    dataset = next(descendants(root, "dataset"), None)
    if dataset is None:
        return []
    out: list[EmlEntity] = []
    for element in dataset:
        entity_type = element.tag.rsplit("}", 1)[-1]
        if entity_type not in ENTITY_TYPES:
            continue
        physical = child(element, "physical")
        url = None
        size = None
        fmt = None
        object_name = None
        if physical is not None:
            object_name = text_of(physical, "objectName")
            size = size_bytes(next(children(physical, "size"), None))
            url = next(
                (
                    " ".join(u.text.split())
                    for u in descendants(physical, "url")
                    if u.text and u.text.strip()
                ),
                None,
            )
            data_format = child(physical, "dataFormat")
            if data_format is not None:
                fmt = text_of(data_format, "externallyDefinedFormat", "formatName") or (
                    "text" if child(data_format, "textFormat") is not None else None
                )
        match = _PASTA_ENTITY_RE.search(url or "")
        name = text_of(element, "entityName")
        if match:
            entity_id: str | None = match.group("entity")
        else:
            entity_id = pasta_entity_id(name) if name else None
        out.append(
            EmlEntity(
                name=name,
                entity_type=entity_type,
                object_name=object_name,
                url=url,
                entity_id=entity_id,
                size=size,
                format=fmt,
            )
        )
    return out


__all__ = ["ENTITY_TYPES", "EmlEntity", "entity_refs", "pasta_entity_id", "size_bytes"]
