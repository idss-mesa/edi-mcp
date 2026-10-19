"""Hardened XML parsing (DESIGN.md D8).

EML, PASTA search results, DataONE system metadata and resource maps are
untrusted: they are parsed with ``defusedxml`` only (no entity expansion, no
external DTDs). Helpers work on local names so namespace prefixes, which vary
across EML versions, do not matter.
"""

from __future__ import annotations

from collections.abc import Iterator
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from edi_mcp.errors import EdiApiError


def parse_xml(data: bytes | str, *, source: str, service: str = "PASTA") -> Element:
    """Parse ``data`` safely; failures become a ``decode`` :class:`EdiApiError`."""
    try:
        root: Element = fromstring(data)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise EdiApiError(
            200,
            f"response is not usable XML ({type(exc).__name__})",
            source,
            kind="decode",
            content_type="application/xml",
            service=service,
        ) from None
    return root


def local(tag: str) -> str:
    """``{namespace}name`` -> ``name``."""
    return tag.rsplit("}", 1)[-1]


def children(element: Element, name: str) -> Iterator[Element]:
    """Direct children with local name ``name``."""
    return (c for c in element if local(c.tag) == name)


def child(element: Element | None, name: str) -> Element | None:
    """First direct child named ``name``; ``None`` (never a falsy Element test) if absent."""
    if element is None:
        return None
    return next(children(element, name), None)


def descendants(element: Element, name: str) -> Iterator[Element]:
    return (e for e in element.iter() if local(e.tag) == name)


def text_of(element: Element | None, *path: str) -> str | None:
    """Stripped text of the element reached by following ``path`` local names."""
    current = element
    for name in path:
        if current is None:
            return None
        current = child(current, name)
    if current is None or current.text is None:
        return None
    return " ".join(current.text.split()) or None


#: EML TextType blocks whose whole text (inline markup included) is one paragraph.
_PROSE_BLOCKS = frozenset({"para", "title", "markdown", "literalLayout"})


def squash(text: str) -> str:
    return " ".join(text.split())


def prose(element: Element | None) -> str | None:
    """The readable text of an EML TextType element (abstract, methods, rights, …).

    ``para``/``title``/``markdown`` blocks become paragraphs joined by blank lines, with
    inline markup (``emphasis``, ``ulink``, ``subscript``, …) kept as text via
    ``itertext()``; sections and lists are walked in document order. An element
    without such blocks (EML 2.0 plain text) yields all of its text.
    """
    if element is None:
        return None
    blocks: list[str] = []

    def visit(node: Element) -> None:
        if local(node.tag) in _PROSE_BLOCKS:
            text = squash("".join(node.itertext()))
            if text:
                blocks.append(text)
            return
        for sub in node:
            visit(sub)

    visit(element)
    if not blocks:
        text = squash("".join(element.itertext()))
        return text or None
    return "\n\n".join(blocks)


__all__ = [
    "child",
    "children",
    "descendants",
    "local",
    "parse_xml",
    "prose",
    "squash",
    "text_of",
]
