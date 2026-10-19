"""Data tools: ``edi_preview_entity``, ``edi_download_entities`` and ``edi_download_package``.

Previews stream an entity and stop reading after a few rows (GMN ignores
``Range``), on both backends. Downloads exist only on stdio (DESIGN.md D17):
they plan before transferring, verify SHA-1 checksums and never overwrite.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from edi_mcp.context import ToolContext
from edi_mcp.edi.backends import PastaBackend
from edi_mcp.edi.downloads import DownloadArea, FileStatus, safe_name, unique_names
from edi_mcp.edi.preview import layout, parse_preview
from edi_mcp.edi.scopes import load_scopes
from edi_mcp.errors import EdiApiError, ToolError
from edi_mcp.models.common import EdiOutput, ToolResultBase
from edi_mcp.registry import register_tool
from edi_mcp.tools._common import merge_notes, source
from edi_mcp.tools.packages import (
    EntityRow,
    Loaded,
    PackageArgs,
    RevisionFrom,
    entity_rows,
    load,
    pick_entities,
)

DEFAULT_ROWS = 20
MAX_ROWS = 200
SHA1_HEADER = "dataone-checksum"


def _not_replicated(loaded: Loaded) -> None:
    """Without a key, data come from DataONE, which does not hold every scope."""
    if loaded.backend.name != "dataone":
        return
    record = load_scopes().get(loaded.resolved.package.scope)
    if record is not None and not record.dataone_replicated:
        raise ToolError(
            "auth_required",
            f"DataONE does not replicate scope {record.scope}, so its data need an EDI API key.",
            details={"scope": record.scope},
            hint="Set EDI_API_KEY to read the data from PASTA (see edi://guide/api-key).",
        )


# ---------------------------------------------------------------------------
# edi_preview_entity
# ---------------------------------------------------------------------------


class PreviewIn(PackageArgs):
    entity: str = Field(
        min_length=1, max_length=300, description="Entity id, name or file name (case-insensitive)."
    )
    rows: int = Field(DEFAULT_ROWS, ge=1, le=MAX_ROWS, description="Data rows to return.")
    max_bytes: int | None = Field(
        None, ge=1024, description="Most bytes to read (capped by limits.preview_max_bytes)."
    )


class PreviewResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "rows"

    package_id: str
    revision_from: RevisionFrom
    entity_id: str | None = None
    name: str | None = None
    size: int | None = Field(None, description="Entity bytes, when known.")
    columns: list[str] = Field(description="Column names (file header, else EML attributes).")
    columns_from: Literal["header", "eml", "none"]
    rows: list[list[str]] = Field(description="Data rows as text; long cells end with '…'.")
    complete: bool = Field(description="True when every row of the entity is shown.")
    bytes_read: int


@register_tool(
    "edi_preview_entity",
    title="Preview a data entity",
    description=(
        "The first rows of one delimited data entity (a CSV or other text table), parsed with "
        "the EML's delimiter, quote character and header lines, with column names. Reads at "
        "most a few hundred KB and stops; works with or without a key (PASTA or the DataONE "
        "member node). Binary entities are refused. Next: call edi_list_entities for column "
        "definitions and units, or edi_download_entities for the whole file."
    ),
    input_model=PreviewIn,
    output_model=PreviewResult,
    surface="data",
    endpoints=[
        "GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/data/eml/{scope}/{id}/{rev}/{entity}",
        "GET gmn.lternet.edu/mn/v2/object/{pid}",
    ],
)
async def edi_preview_entity(args: PreviewIn, ctx: ToolContext) -> PreviewResult:
    loaded = await load(args, ctx)
    _not_replicated(loaded)
    backend, package = loaded.backend, loaded.resolved.package
    rows, notes = await entity_rows(loaded)
    row = pick_entities(rows, [args.entity], package.package_id)[0]
    if row.entity_id is None:
        raise ToolError("not_found", f"Entity {args.entity!r} has no data id to read.")
    fmt = row.meta.text_format if row.meta else None
    plan = layout(
        fmt.field_delimiter if fmt else None,
        fmt.quote_character if fmt else None,
        fmt.header_lines if fmt else None,
    )
    cap = min(
        args.max_bytes or ctx.config.limits.preview_max_bytes, ctx.config.limits.preview_max_bytes
    )
    wanted_lines = plan.header_lines + args.rows + 1
    data = bytearray()
    eof = True
    try:
        async with backend.stream_entity(package, row.entity_id) as stream:
            async for chunk in stream.chunks():
                data.extend(chunk)
                if len(data) >= cap or data.count(b"\n") >= wanted_lines:
                    eof = False
                    break
    except EdiApiError as exc:
        raise backend.not_found(exc, "entity", f"{package}/{row.entity_id}") from None
    if not eof and len(data) > cap:
        del data[cap:]
    preview = parse_preview(bytes(data), eof=eof, fmt=plan, rows=args.rows)
    attribute_names = [a.name for a in row.meta.attributes] if row.meta else []
    columns_from: Literal["header", "eml", "none"]
    if preview.header:
        columns, columns_from = preview.header, "header"
    elif attribute_names:
        columns, columns_from = attribute_names, "eml"
    else:
        columns, columns_from = [], "none"
    notes = list(notes) + plan.notes
    if preview.cells_cut:
        notes.append(f"{preview.cells_cut} long cell(s) were cut to 200 characters.")
    if preview.columns_cut:
        notes.append(f"Only the first 100 columns are shown ({preview.columns_cut} more).")
    if not preview.rows:
        notes.append("No data rows were found in the bytes read.")
    steps = [
        f"edi_list_entities(package='{package.package_id}', entity='{row.entity_id}')",
    ]
    if ctx.config.effective_downloads_enabled(ctx.transport):
        steps.append(
            f"edi_download_entities(package='{package.package_id}', entities=['{row.entity_id}'])"
        )
    return PreviewResult(
        package_id=package.package_id,
        revision_from=loaded.resolved.revision_from,
        entity_id=row.entity_id,
        name=row.name,
        size=row.size,
        columns=columns,
        columns_from=columns_from,
        rows=preview.rows,
        complete=preview.complete,
        bytes_read=len(data),
        resolved=loaded.echoes,
        notes=merge_notes(loaded.notes, backend.notes, notes),
        next_steps=steps,
        source=source(ctx, derived=["columns", "rows"]),
    )


# ---------------------------------------------------------------------------
# Downloads (stdio only)
# ---------------------------------------------------------------------------


class SavedFile(EdiOutput):
    entity_id: str | None = None
    name: str | None = Field(None, description="Entity name, or the file's role (metadata, zip).")
    path: str
    bytes: int | None = None
    sha1_verified: bool | None = Field(
        None, description="True/false against EDI's SHA-1; null when none is published."
    )
    status: FileStatus
    error: str | None = None


class DownloadResult(ToolResultBase):
    package_id: str
    directory: str = Field(description="Where the files were saved.")
    files: list[SavedFile]
    downloaded: int
    bytes: int = Field(description="Bytes transferred by this call.")


def _require_downloads(ctx: ToolContext) -> DownloadArea:
    if not ctx.config.effective_downloads_enabled(ctx.transport):
        raise ToolError(
            "feature_unavailable",
            "Downloads are disabled (stdio only, and downloads.enabled is not false).",
        )
    return DownloadArea(ctx.config.downloads)


class DownloadEntitiesIn(PackageArgs):
    entities: list[str] | None = Field(
        None, max_length=200, description="Entity ids, names or file names; all when omitted."
    )
    include_metadata: bool = Field(True, description="Also save the EML as <packageId>.xml.")
    dest_subdir: str | None = Field(
        None, max_length=200, description="Sub-directory of the download directory."
    )
    max_bytes: int | None = Field(None, ge=1, description="Refuse plans larger than this.")


async def _expected_sha1(loaded: Loaded, row: EntityRow) -> str | None:
    if row.info is not None and row.info.sha1:
        return row.info.sha1.lower()
    if row.entity_id is None:
        return None
    try:
        return await loaded.backend.entity_checksum(loaded.resolved.package, row.entity_id)
    except ToolError:
        return None


@register_tool(
    "edi_download_entities",
    title="Download data entities",
    description=(
        "Save a package's data entities (all, or the ones named) and its EML into the "
        "configured download directory (stdio only). The plan is checked against file and byte "
        "caps first; SHA-1 checksums are verified; existing identical files are skipped and "
        "different ones are never overwritten. Works with or without a key. Next: read the "
        "files (pandas.read_csv) and cite with edi_get_citation."
    ),
    input_model=DownloadEntitiesIn,
    output_model=DownloadResult,
    surface="data",
    endpoints=[
        "GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/data/eml/{scope}/{id}/{rev}/{entity}",
        "GET pasta.lternet.edu/package/data/checksum/eml/{scope}/{id}/{rev}/{entity}",
        "GET gmn.lternet.edu/mn/v2/object/{pid}",
        "GET gmn.lternet.edu/mn/v2/meta/{pid}",
    ],
    transports=("stdio",),
    read_only=False,
    idempotent=True,
    needs_downloads=True,
)
async def edi_download_entities(args: DownloadEntitiesIn, ctx: ToolContext) -> DownloadResult:
    area = _require_downloads(ctx)
    subdir = area.clean_subdir(args.dest_subdir)
    loaded = await load(args, ctx)
    _not_replicated(loaded)
    backend, package = loaded.backend, loaded.resolved.package
    rows, notes = await entity_rows(loaded)
    chosen = [r for r in pick_entities(rows, args.entities, package.package_id) if r.entity_id]
    if not chosen:
        raise ToolError("not_found", f"Package {package.package_id} has no downloadable entity.")
    known = sum(r.size or 0 for r in chosen)
    cap = area.check_plan(len(chosen), known, args.max_bytes)
    folder = package.package_id
    names = unique_names(
        [safe_name(r.object_name or r.name or r.entity_id or "entity") for r in chosen]
    )
    renamed = [
        f"{r.object_name or r.name} → {n}"
        for r, n in zip(chosen, names, strict=True)
        if (r.object_name or r.name) and (r.object_name or r.name) != n
    ]
    if renamed:
        notes.append("Saved under safe file names: " + "; ".join(renamed[:10]) + ".")
    files: list[SavedFile] = []
    if args.include_metadata and loaded.body:
        meta_path = area.destination(subdir, folder, f"{package.package_id}.xml")
        status: FileStatus = "skipped" if meta_path.exists() else "downloaded"
        if status == "downloaded":
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            with meta_path.open("xb") as handle:
                handle.write(loaded.body)
        files.append(
            SavedFile(
                name="metadata (EML)", path=str(meta_path), bytes=len(loaded.body), status=status
            )
        )
    moved = 0
    for row, name in zip(chosen, names, strict=True):
        entity_id = row.entity_id or ""
        dest = area.destination(subdir, folder, name)
        expected = (
            await _expected_sha1(loaded, row) if ctx.config.downloads.verify_checksums else None
        )
        same = area.existing_matches(dest, row.size, expected)
        if same is not None:
            files.append(
                SavedFile(
                    entity_id=entity_id,
                    name=row.name,
                    path=str(dest),
                    bytes=dest.stat().st_size,
                    sha1_verified=True if same and expected else None,
                    status="skipped" if same else "conflict",
                    error=None if same else "a different file exists here; it was not overwritten",
                )
            )
            continue
        limit = min(ctx.config.downloads.max_file_bytes, cap - moved)
        try:
            async with backend.stream_entity(
                package,
                entity_id,
                allowed_hosts=ctx.config.downloads.allowed_hosts,
                read_timeout_s=ctx.config.edi.download_read_timeout_s,
            ) as stream:
                header = stream.header(SHA1_HEADER) or ""
                if expected is None and header.upper().startswith("SHA-1,"):
                    expected = header.split(",", 1)[1].strip().lower() or None
                written = await area.write(stream.chunks(), dest, max_bytes=limit, label=name)
        except (ToolError, EdiApiError) as exc:
            err = exc if isinstance(exc, ToolError) else backend.not_found(exc, "entity", entity_id)
            files.append(
                SavedFile(
                    entity_id=entity_id,
                    name=row.name,
                    path=str(dest),
                    status="failed",
                    error=f"{err.code}: {err.message}",
                )
            )
            continue
        verified = None
        if expected and ctx.config.downloads.verify_checksums:
            verified = written.sha1 == expected
            if not verified:
                dest.unlink(missing_ok=True)
        moved += written.bytes
        files.append(
            SavedFile(
                entity_id=entity_id,
                name=row.name,
                path=str(dest),
                bytes=written.bytes,
                sha1_verified=verified,
                status="downloaded" if verified is not False else "failed",
                error=None
                if verified is not False
                else "checksum_mismatch: the SHA-1 did not match EDI's; the file was removed",
            )
        )
    if any(f.status == "conflict" for f in files):
        notes.append(
            "Some files already existed with different contents and were left untouched; "
            "use dest_subdir to save this revision elsewhere."
        )
    return DownloadResult(
        package_id=package.package_id,
        directory=str(area.destination(subdir, folder)),
        files=files,
        downloaded=sum(1 for f in files if f.status == "downloaded" and f.entity_id),
        bytes=moved,
        resolved=loaded.echoes,
        notes=merge_notes(loaded.notes, backend.notes, notes),
        next_steps=[f"edi_get_citation(package='{package.package_id}')"],
        source=source(ctx),
    )


class DownloadPackageIn(PackageArgs):
    dest_subdir: str | None = Field(
        None, max_length=200, description="Sub-directory of the download directory."
    )
    max_bytes: int | None = Field(None, ge=1, description="Stop and fail beyond this many bytes.")


@register_tool(
    "edi_download_package",
    title="Download a whole package (zip)",
    description=(
        "Save one package revision as PASTA's zip archive (metadata, data entities, quality "
        "report) into the configured download directory (stdio only; needs an EDI API key). "
        "Archives can be very large: the transfer stops at the byte cap, and an existing "
        "file is never overwritten. Next: unzip it, or prefer edi_download_entities for "
        "chosen files."
    ),
    input_model=DownloadPackageIn,
    output_model=DownloadResult,
    surface="data",
    endpoints=["GET pasta.lternet.edu/package/download/eml/{scope}/{id}/{rev}"],
    requires_key=True,
    transports=("stdio",),
    read_only=False,
    idempotent=True,
    needs_downloads=True,
)
async def edi_download_package(args: DownloadPackageIn, ctx: ToolContext) -> DownloadResult:
    area = _require_downloads(ctx)
    subdir = area.clean_subdir(args.dest_subdir)
    loaded = await load(args, ctx)
    backend, package = loaded.backend, loaded.resolved.package
    if not isinstance(backend, PastaBackend):  # pragma: no cover - the registry requires a key
        raise ToolError("auth_required", "Whole-package downloads need an EDI API key.")
    rows, notes = await entity_rows(loaded)
    cap = area.check_plan(1, sum(r.size or 0 for r in rows), args.max_bytes)
    limit = min(cap, ctx.config.downloads.max_file_bytes)
    name = f"{package.package_id}.zip"
    dest = area.destination(subdir, name)
    if dest.exists():
        files = [
            SavedFile(
                name="package (zip)",
                path=str(dest),
                bytes=dest.stat().st_size,
                status="skipped",
                error="the archive already exists; it was not downloaded again",
            )
        ]
        moved = 0
    else:
        try:
            async with backend.stream_package_zip(
                package,
                allowed_hosts=ctx.config.downloads.allowed_hosts,
                read_timeout_s=ctx.config.edi.download_read_timeout_s,
            ) as stream:
                length = stream.header("content-length")
                if length and length.isdigit() and int(length) > limit:
                    raise ToolError(
                        "download_limit_exceeded",
                        f"The archive is {int(length)} bytes, above the limit of {limit}.",
                        details={"bytes": int(length), "maxBytes": limit},
                        hint="Download chosen entities with edi_download_entities instead.",
                    )
                written = await area.write(stream.chunks(), dest, max_bytes=limit, label=name)
        except EdiApiError as exc:
            raise backend.not_found(exc, "package", str(package)) from None
        moved = written.bytes
        files = [
            SavedFile(
                name="package (zip)", path=str(dest), bytes=written.bytes, status="downloaded"
            )
        ]
    return DownloadResult(
        package_id=package.package_id,
        directory=str(area.destination(subdir, name).parent),
        files=files,
        downloaded=sum(1 for f in files if f.status == "downloaded"),
        bytes=moved,
        resolved=loaded.echoes,
        notes=merge_notes(loaded.notes, backend.notes, notes),
        next_steps=[f"edi_get_citation(package='{package.package_id}')"],
        source=source(ctx),
    )
