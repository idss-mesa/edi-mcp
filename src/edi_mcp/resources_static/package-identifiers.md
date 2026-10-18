# EDI package identifiers

## Anatomy

An EDI data package is identified by **scope.identifier.revision**:

| Part | Example | Meaning |
|---|---|---|
| scope | `knb-lter-hbr`, `edi` | Namespace. `knb-lter-<site>` for each LTER site (hbr = Hubbard Brook, jrn = Jornada, ntl = North Temperate Lakes, …); `edi` for the general EDI scope; others such as `ecotrends`, `cos-spu`. |
| identifier | `14`, `210548103` | Integer, unique within the scope. |
| revision | `22` | Integer, incremented on every update. Old revisions stay available. |

`knb-lter-hbr.14.22` is revision 22 of package 14 in the Hubbard Brook scope. Path
forms use slashes: `knb-lter-hbr/14/22`.

`newest` and `oldest` stand for the latest and first revision.

## Other identifiers

- **DOI:** every revision has its own DOI, `doi:10.6073/pasta/<32 hex>`, resolvable
  at `https://doi.org/10.6073/pasta/<32 hex>`.
- **Landing page:**
  `https://portal.edirepository.org/nis/mapbrowse?scope=knb-lter-hbr&identifier=14&revision=22`.
- **Data entity:** a package's tables and files are *entities*, each with a 32-hex
  entity id (e.g. `c606bfe2f2deb3fa3eabf692ae15f02d`) and a name such as
  "Daily Watershed Precipitation". Entity URLs look like
  `https://pasta.lternet.edu/package/data/eml/knb-lter-hbr/14/22/<entityId>`.
- **DataONE identifiers:** in DataONE, the EML document's identifier is its PASTA URL
  (`https://pasta.lternet.edu/package/metadata/eml/knb-lter-hbr/14/22`), and the
  package's resource map is its DOI.

## What edi-mcp accepts

Wherever a tool takes a package, any of these work, and the normalized `packageId` is
echoed in `resolved`:

- `knb-lter-hbr.14.22`, `knb-lter-hbr/14/22`
- `knb-lter-hbr.14` (with a `revision` argument, default `newest`)
- `doi:10.6073/pasta/…`, `https://doi.org/10.6073/pasta/…`
- portal `mapbrowse?scope=…&identifier=…&revision=…` URLs
- PASTA package, metadata and data URLs
- a site code or scope name in place of the scope: `jrn.210548103`,
  `Jornada Basin.210548103.43`

## Scope names and site codes

Scope arguments (`scope=` and the scope part of a package) accept:

- the exact scope: `knb-lter-jrn`, `edi`, `msb-cap`;
- an LTER site code, any case: `JRN`, `hbr`. Three-letter codes always mean the LTER
  site, so `cap` is Central Arizona-Phoenix (`knb-lter-cap`); use `msb-cap` exactly for
  the Macrosystems scope;
- a name, alias or location: `Jornada`, `Hubbard Brook`, `Toolik`, `Kansas`.

A match is accepted when it is clear (score at least 0.75 and 1.15 times the runner-up)
and echoed in `resolved` with its confidence. A shared name or location returns
`ambiguous_input` with ranked candidates: `Alaska` (four sites), `New Mexico`
(Jornada, Sevilleta), `Landsat` (two bulk scopes). A hyphenated code edi-mcp does not
know yet passes through unchanged, so scopes newer than the snapshot still work with a
key. `edi://reference/scopes` lists every scope, and `edi_list_scopes` lists them live
when a key is set.
