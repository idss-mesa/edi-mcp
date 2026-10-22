# Citing EDI data

The packages edi-mcp finds belong to their creators and are published by the
Environmental Data Initiative (EDI). Each package's intellectual rights, together with
EDI's data policy (https://edirepository.org/about/edi-policy), govern how the data
may be used and credited.

## Cite one revision, by its DOI

A package is `scope.identifier.revision` (`knb-lter-hbr.14.22`). Published revisions
never change: an update is a new revision with its own DOI,
`doi:10.6073/pasta/<md5>`. Cite the revision you actually used so that others get the
same data, and never cite PASTA, DataONE or download URLs.

## Getting the citation

`edi_get_citation(package="knb-lter-hbr.14.22", style="ESIP")` asks EDI's citation
service (cite.edirepository.org, no key needed) and returns the formatted text plus
its parts (authors, title, year, version, publisher, DOI, URL). Styles:

* **ESIP** (default): `Authors. Year. Title ver N. Environmental Data Initiative. https://doi.org/10.6073/pasta/<md5>.`
* **DRYAD**: `Authors (Year) Title. Environmental Data Initiative. https://doi.org/...`
* **BIBTEX**: a `@misc{scope.identifier.revision, ...}` entry with `doi` and `url`.

A package the service cannot cite (missing, or access-restricted) returns
`not_found`. Passing a series (`knb-lter-hbr.14`) cites the newest revision; without a
key that is DataONE's newest, which can lag PASTA, and a note says so.

## Rights

Read the `rights` section of `edi_get_metadata`. EDI encourages open access and, when
a provider declares no license, applies a statement based on CC0 1.0 that still asks
for attribution. Some packages declare stricter terms, and some are access-restricted
(`upstream_forbidden` with `reason: access_restricted`).

## Mentioning edi-mcp

You may mention edi-mcp in a methods section, but the citation of record is the data
package DOI. edi-mcp is not affiliated with or endorsed by EDI, the LTER Network or
DataONE.
