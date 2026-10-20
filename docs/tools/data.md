---
title: "Previews and downloads"
description: "Read the first rows of a delimited data entity with edi_preview_entity on either backend, and save entities, their EML or a whole package zip into the download directory with edi_download_entities and edi_download_package (stdio only)."
type: Guide
tags:
  - tools
  - data
  - preview
  - downloads
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
  - id: dataone-mn
    resource: "https://dataoneorg.github.io/api-documentation/apis/MN_APIs.html"
    title: "DataONE Member Node APIs"
    author: "team:dataone"
status: stable
---

# Previews and downloads

Three tools read the data themselves:
[`edi_preview_entity`](reference.md#edi_preview_entity) shows the first rows of one
table, [`edi_download_entities`](reference.md#edi_download_entities) saves entities to
disk, and [`edi_download_package`](reference.md#edi_download_package) saves a whole
package as PASTA's zip archive. All take the `package` and `revision` inputs described
in [Packages, metadata and entities](packages.md); entities are named by id, name or
file name, case-insensitively, as [`edi_list_entities`](reference.md#edi_list_entities)
lists them.

With an EDI API key the bytes come from PASTA; without one they come from the
scope's DataONE member node, which serves the same objects anonymously (see
[Backends](backends.md)). Scopes that edi-mcp's dated snapshot shows DataONE does not
replicate (`cos-spu`, `icarus`, …) fail with `auth_required` before any request is
made.

## edi_preview_entity

The preview streams the entity and stops reading as soon as it has the rows it needs,
or at `max_bytes` (at most `limits.preview_max_bytes`, 256 KiB by default). Reading
stops early because the member nodes ignore HTTP `Range`.

- **Layout from the EML.** The field delimiter, quote character and number of header
  lines come from the entity's `textFormat`. Delimiters written as escape text or
  words (`\t`, `tab`, `#x09`, `\r\n`) are unescaped. When the EML names no delimiter,
  a comma is assumed, and a note says so.
- **Header detection.** When the EML gives no header-line count, the first line is
  taken as the header if it names at least half of the EML's attribute names (or, with
  no attributes, if Python's `csv.Sniffer` thinks it is one); a note says which way it
  went. `columnsFrom` reports where `columns` came from: `header`, `eml` (attribute
  names) or `none`.
- **Rows.** `rows` (default 20, at most 200) data rows as text. A record cut off by
  the early stop is dropped. Cells longer than 200 characters are cut and end with
  `…`; only the first 100 columns are kept. `complete` is true when the whole entity
  was read.
- **Binary data** (a NUL byte in the first 8 KiB) is refused with `invalid_argument`;
  download it instead.

## Downloads (stdio only)

The two download tools are the only tools that write. They are offered only over
stdio and only while `downloads.enabled` is not `false`; over HTTP they are never
listed. Everything is written under `downloads.directory` (`~/edi-downloads` by
default; see [Configuration](../getting-started/configuration.md)), optionally in a
relative `dest_subdir` made of letters, digits, `.`, `_`, `-` and `/`. Absolute paths,
`..`, backslashes and symlinks that lead outside the directory are refused with
`download_denied`.

### edi_download_entities

Saves the chosen entities (all of them when `entities` is omitted) into
`<download dir>/[dest_subdir/]<packageId>/`, and, unless `include_metadata` is false,
the EML as `<packageId>.xml` beside them.

1. **Plan first.** The number of entities and their known sizes are checked against
   `downloads.max_files_per_call`, `downloads.max_bytes_per_call` and the call's
   `max_bytes` before anything is transferred; a plan over a limit fails with
   `download_limit_exceeded`. Each file is also capped at `downloads.max_file_bytes`
   while it streams.
2. **Safe names.** Files are saved under their EML object name, made safe (spaces and
   other characters become `_`) and de-duplicated; renamed files are listed in
   `notes`.
3. **Checksums.** The SHA-1 EDI publishes comes from PASTA's checksum service (with a
   key) or the member node's `DataONE-Checksum` header. `sha1Verified` is true or
   false against it, or absent when none is published. A file whose SHA-1 differs is
   removed and reported with status `failed` (`checksum_mismatch: …`).
4. **Never overwrite.** Each file streams to a `.part` file and is linked into place
   only if nothing exists there. An existing identical file is `skipped`; an existing
   different file is reported as `conflict` and left untouched; use `dest_subdir` to
   save another revision elsewhere.

Every redirect hop must be on `downloads.allowed_hosts`. Each saved file is reported
with its path, bytes and status (`downloaded`, `skipped`, `conflict` or `failed`), and
`bytes` totals what this call transferred.

### edi_download_package

Saves PASTA's zip archive of one revision (metadata, data entities and quality
report) as `<download dir>/[dest_subdir/]<packageId>.zip`. It needs an EDI API key,
since DataONE has no archive. Archives can be very large: the plan is checked against
the package's known entity bytes, an archive whose `Content-Length` exceeds the cap is
refused before writing, and the stream stops at the cap otherwise, removing the
partial file. An existing archive is skipped, never replaced. Prefer
`edi_download_entities` when only some files are needed.

## Typical flow

1. `edi_list_entities` → choose an entity and check its size.
2. `edi_preview_entity` → confirm the columns and missing-value codes look right.
3. `edi_download_entities(entities=[…])` → save it with its EML, SHA-1 verified.
4. `edi_get_citation` → cite the revision you used (see
   [Citations, quality reports and lineage](citation-and-quality.md)).
