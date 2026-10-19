---
title: "Citations, quality reports and lineage"
description: "Cite a package revision with edi_get_citation, read PASTA's quality checks with edi_get_quality_report (with or without a key), and follow provenance with edi_get_lineage (key required)."
type: Guide
tags:
  - tools
  - citation
  - quality
  - provenance
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: cite
    resource: "https://cite.edirepository.org/"
    title: "EDI citation service"
    author: "team:edi"
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
  - id: edi-policy
    resource: "https://edirepository.org/about/edi-policy"
    title: "EDI data policy"
    author: "team:edi"
status: stable
---

# Citations, quality reports and lineage

## edi_get_citation

[`edi_get_citation`](reference.md#edi_get_citation) returns a formatted citation for
one package revision from EDI's citation service, `cite.edirepository.org`, which
needs no key. `style` is `ESIP` (the default), `DRYAD` or `BIBTEX` (a `@misc` entry).
Beside the text, `parts` gives the authors, year, title, version, publisher and DOI
(normalised to `doi:10.6073/pasta/<md5>`, with `doiUrl`), and `portalUrl` the EDI Data
Portal page.

- A series (`knb-lter-hbr.14`) resolves to its newest revision on the call's backend
  first; `source.backend` is then `mixed`, and `cite` when only the citation service
  was asked.
- The service has no citation for packages that do not exist or are
  access-restricted; both fail with `not_found` and a hint.
- A note reminds you to cite the exact revision by DOI and to check the package's
  license with `edi_get_metadata(include=['rights'])`. See
  [Citing EDI data](../about/citing-edi.md).

## edi_get_quality_report

[`edi_get_quality_report`](reference.md#edi_get_quality_report) summarises the quality
report PASTA wrote when the revision was published: congruence checks of the metadata
and of each data entity against its EML. It works **with or without a key**: PASTA's
reports are replicated to the DataONE member nodes, which serve them anonymously
(verified 2026-10-19 on both nodes). Scopes DataONE does not replicate need a key.

- `counts` gives the checks by status (`valid`, `info`, `warn`, `error`) over the
  dataset and all entities.
- `issues` lists the non-valid checks, errors first, with EDI's name, what was found,
  the explanation and the suggestion (long text is cut); `entity` names the entity a
  check belongs to. `include_info` adds the `info` checks. At most 50 are listed;
  `issuesTotal` counts them all.
- `entities` gives each entity's own counts (`entitiesTotal` counts them all).

## edi_get_lineage

[`edi_get_lineage`](reference.md#edi_get_lineage) needs an EDI API key. It lists the
EDI packages a revision was derived from (`sources`, the data sources named in its
EML methods) and the packages that name it as a source (`descendants`), each with its
`packageId`, title and metadata URL. PASTA escapes these titles twice; edi-mcp decodes
them. `nextSteps` points at `edi_get_package` for the first few.
