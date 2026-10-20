---
title: "Change feed and read counts"
description: "List packages inserted, updated or deleted in PASTA during a date window with edi_recent_changes, and see how often a package series or revision has been read with edi_get_read_counts; both need an EDI API key."
type: Guide
tags:
  - tools
  - feeds
  - audit
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
status: stable
---

# Change feed and read counts

Both tools read PASTA services that have no DataONE counterpart, so they need an EDI
API key; without one they fail at once with `auth_required` (see
[EDI API key](../getting-started/api-key.md)).

## edi_recent_changes

[`edi_recent_changes`](reference.md#edi_recent_changes) reads PASTA's change feed
(`/package/changes/eml`): every package inserted (a new package), updated (a new
revision) or deleted during a window of days.

- `from_date` and `to_date` are `YYYY-MM-DD` days in UTC, both inclusive. The default
  window is the last 7 days; the longest is 92 days, so split longer periods into
  several calls.
- `scope` narrows the feed to one scope (a scope code, LTER site code or name, resolved
  as in [Identifiers and scope names](identifiers.md)); `kinds` keeps only `insert`,
  `update` or `delete` entries.
- Changes come newest first with their `packageId`, `kind`, ISO 8601 `date` and DOI,
  paged with `offset` and `limit` (default 25, at most 200). `counts` tallies the whole
  window by kind, before the `kinds` filter.
- The upstream feed names the EDI user who made each change; edi-mcp drops that
  identifier, so it never appears in a result.

## edi_get_read_counts

[`edi_get_read_counts`](reference.md#edi_get_read_counts) reads PASTA's audit service
(`/audit/reads`). Give a series (`knb-lter-hbr.14`) for every revision, or one revision
(`knb-lter-hbr.14.22`, or the series plus `revision`); a DOI names one revision.

- `totals` gives total and non-robot reads by resource type: `dataPackage`,
  `metadata`, `report`, `data` (all entities) and `archive` (zip downloads), as PASTA
  reports them.
- `revisions` lists each revision, newest first (at most 100, `revisionsTotal` counts
  them all), with the package's and its data entities' reads.
