# edi-mcp — verified research

Facts below carry the date they were verified. Re-verify anything that contradicts
observed behaviour.

## 1. PASTA authentication (verified 2026-10-17)

- EDI announced on 2026-07-27 that the PASTA REST API requires authentication for all
  users from **2026-07-30** (https://edirepository.org/news/news-20260727.00). Users sign
  in at https://auth.edirepository.org (Google, Microsoft, GitHub, ORCiD) and create an
  **API key** in their profile.
- Anonymous requests to `/package/eml`, `/package/eml/{s}/{i}`, `/package/search/eml`
  and `/package/metadata/eml/...` return **403 text/plain**:
  `User 'EDI-… (Public Access)' is not authorized to execute service method '…'`.
  Staging `pasta-s.lternet.edu` behaves the same.
- Credential forms PASTA recognises (bogus-value responses below; valid-key results in
  "Step 1 probe results"):
  - `?key=<API key>` → bogus key gives `401 API key resolution failed` (EDIutils
    `add_api_key()` uses this form);
  - `Cookie: edi-token=<JWT>` → bogus gives `401 EDI token validation failed`;
  - HTTP Basic with a legacy DN; `Authorization: Bearer` gives
    `400 Basic Authorization header not sent in request`.
- Key exchange: `POST https://auth.edirepository.org/auth/v1/key` `{"key": …}` →
  `{"edi-token": JWT}`; refresh `POST /auth/v1/token/refresh` `{"edi-token": …}`. The
  public-access JWT has a lifetime of 28 800 s (8 h).

### Step 1 probe results (verified 2026-10-17 with a real profile-principal key)

`scripts/probe_auth.py` against `knb-lter-hbr.14.22` (newest revision of `knb-lter-hbr.14`):

- **Key → token exchange works:** `POST /auth/v1/key` → 200 with `edi-token`; JWT
  lifetime exactly 28 800 s (8 h). **Refresh works:** `POST /auth/v1/token/refresh` → 200
  with a new token. The token's `principals` claim lists the profile plus the system
  principals Public Access, Human Access and Authenticated Access.
- **Both credential forms are accepted on every read method tested:**

| Service method | Path | Anonymous | `Cookie: edi-token` | `?key=` | Content-Type |
|---|---|---|---|---|---|
| listDataPackageScopes | `/package/eml` | 403 | 200 | 200 | text/plain |
| listDataPackageIdentifiers | `/package/eml/{s}` | 403 | 200 | 200 | text/plain |
| listDataPackageRevisions | `/package/eml/{s}/{i}?filter=newest` | 403 | 200 | 200 | text/plain |
| readDataPackage | `/package/eml/{s}/{i}/{r}` | 403 | 200 | 200 | text/plain (entity URLs) |
| readMetadata | `/package/metadata/eml/{s}/{i}/{r}` | 403 | 200 | 200 | application/xml |
| readDataEntityNames | `/package/name/eml/{s}/{i}/{r}` | 403 | 200 | 200 | **text/csv** (`id,name`) |
| readDataEntitySizes | `/package/data/size/eml/{s}/{i}/{r}` | 403 | 200 | 200 | **text/csv** (`id,bytes`) |
| readDataEntityChecksum | `/package/data/checksum/eml/…/{entity}` | 403 | 200 | 200 | text/plain (SHA-1) |
| readDataPackageDoi | `/package/doi/eml/{s}/{i}/{r}` | 403 | 200 | 200 | text/plain |
| readDataPackageReport | `/package/report/eml/{s}/{i}/{r}` | 403 | 200 | 200 | application/xml (`qr:qualityReport`) |
| readDataSources | `/package/sources/eml/{s}/{i}/{r}` | 403 | 200 | 200 | application/xml (`dataSources`) |
| searchDataPackages | `/package/search/eml?defType=edismax&q=streamflow…` | 403 | 200 | 200 | application/xml (`resultset numFound='291'`) |
| listDataChanges | `/package/changes/eml?fromDate=…&scope=…` | 403 | 200 | 200 | application/xml (`dataPackageChanges`) |
| listRecentUploads | `/package/uploads/eml?type=insert&limit=2` | 403 | 200 | 200 | application/xml (`dataPackageUploads`) |
| getReadCounts | `/audit/reads/{s}/{i}` | **401** | 200 | 200 | application/xml (`resourceReads`) |

- Anonymous audit calls return **401** "not authorized to retrieve entries from the audit
  manager", not the 403 the package service returns; map both to `auth_required`.
- `/package/eml` lists `cos-spu`, `ecotrends`, `edi`, `icarus`, `knb-lter-*`, … scopes.

## 2. Anonymous DataONE route (verified 2026-10-17)

| Purpose | URL |
|---|---|
| Search (CN Solr, JSON) | `https://cn.dataone.org/cn/v2/query/solr/?q=formatType:METADATA AND datasource:("urn:node:EDI" OR "urn:node:LTER") AND -obsoletedBy:* AND keywords:streamflow&fl=id,title,resourceMap&wt=json` |
| EML | `https://gmn.lternet.edu/mn/v2/object/{urlencoded PID}` (`knb-lter-*`), `https://gmn.edirepository.org/mn/v2/object/{PID}` (`edi.*`), or `https://cn.dataone.org/cn/v2/object/{PID}` |
| System metadata | `https://gmn.lternet.edu/mn/v2/meta/{PID}` (size, SHA-1, formatId, obsoletes) |
| Data entity | `https://gmn.lternet.edu/mn/v2/object/https%3A%2F%2Fpasta.lternet.edu%2Fpackage%2Fdata%2Feml%2Fknb-lter-hbr%2F14%2F22%2Fc4f72fa0cb155f1b61f1333bb67e3d00` (CSV, `DataONE-Checksum: SHA-1,…`) |
| Resolve PID | `https://cn.dataone.org/cn/v2/resolve/{PID}` (303 to a member node) |
| Resource map | `https://gmn.edirepository.org/mn/v2/object/doi:10.6073%2Fpasta%2F<md5>` |
| Citation | `https://cite.edirepository.org/cite/{packageId}?style=ESIP` (also DRYAD, BIBTEX; `Accept: application/json` for fields) |

- DataONE PIDs for PASTA content: metadata
  `https://pasta.lternet.edu/package/metadata/eml/{s}/{i}/{r}`, data
  `https://pasta.lternet.edu/package/data/eml/{s}/{i}/{r}/{entityId}`, report
  `https://pasta.lternet.edu/package/report/eml/{s}/{i}/{r}`, resource map
  `doi:10.6073/pasta/{md5}`. Pre-PASTA records use `knb-lter-sbc.13.16`-style ids.
- GMN responses carry `DataONE-Proxy: https://pasta.lternet.edu/...`: GMN proxies PASTA
  and could be locked down too. GMN has no Solr (`/mn/v2/query` 404); search via the CN.
- CN Solr lags: `knb-lter-hbr.14.22` (uploaded 2026-10-16) is served by GMN but was not
  yet in CN Solr. `knb-lter-hbr/2/20` is **404** in DataONE (newest there is 2/15); do
  not use it as a fixture.
- Solr includes superseded revisions, but `obsoletedBy` is missing on some of them
  (`knb-lter-hbr/14/9`, `/14/20`, `knb-lter-jrn/210548103/2`) and some `obsoletes` values
  are malformed (`https://pasta/lternet/edu/package/eml/...`). Parse revisions from `id`.
- Solr `documents`/`resourceMap` are present for `edi.*` and `knb-lter-jrn` records but
  absent for `knb-lter-hbr.14.21`, whose data objects are not indexed either. The
  citation service's JSON (`Accept: application/json`) carries the DOI
  (`"doi": "https://doi.org/10.6073/pasta/<md5>."`, note the trailing period).
- `https://cn.dataone.org/cn/v2/object/doi:10.6073%2Fpasta%2F<md5>` returns the ORE
  resource map (`application/rdf+xml`); it names the EML through URL-encoded CN
  `/resolve/` links. CN `/resolve/doi:…` answers 303 to the member node.
- Scopes `cos-spu` and `icarus` are not in DataONE at all; `ecotrends` is (urn:node:LTER).
- PASTA data entity ids are the MD5 of the EML `entityName` (checked on three
  `knb-lter-hbr.14.22` entities; e.g. `md5("thiessen_weights")` =
  `c4f72fa0cb155f1b61f1333bb67e3d00`).
- CN Solr accepts `defType=edismax` with `qf`.
- Useful CN Solr fields: id, title, abstract, keywords, site, beginDate, endDate,
  pubDate, bounding coordinates, attributeName/Unit, `sem_annotation`, `documents`,
  `resourceMap`, `obsoletes`/`obsoletedBy`, size, checksum, formatId, `isPublic`.

## 3. PASTA read endpoints (base `https://pasta.lternet.edu/package`; all auth-gated)

From https://pasta.lternet.edu/package/docs/api. `{r}` may be `newest`/`oldest` where noted.

- Listing (text/plain): `/eml`, `/eml/{s}`, `/eml/{s}/{i}[?filter=newest|oldest]`, `/eml/deleted`.
- Package: `/eml/{s}/{i}/{r}` (resource map; `?ore` for RDF), `/doi/eml/{s}/{i}/{r}`,
  `/download/eml/{s}/{i}/{r}` (zip), `/rmd/eml/…`.
- Metadata: `/metadata/eml/{s}/{i}/{r}` (EML XML), `/metadata/dc/…`, `/metadata/checksum/eml/…`.
- Entities: `/data/eml/{s}/{i}/{r}` (ids), `/data/eml/…/{entityId}` (bytes),
  `/name/eml/…[/{entityId}]` (`id,name`), `/data/size/eml/…` (`id,size`),
  `/data/checksum/eml/…/{entityId}` (SHA-1), `/data/rmd/eml/…/{entityId}`.
- Quality report: `/report/eml/{s}/{i}/{r}` (XML, or HTML with `Accept: text/html`).
- Provenance: `/provenance/eml/…`, `/sources/eml/…`, `/descendants/eml/…`.
- Search: `/search/eml?q=&fl=&fq=&rows=&start=&sort=` (Solr, XML `<resultset numFound>`;
  EDIutils adds `defType=edismax`; newest revisions only; `fq=-scope:(ecotrends lter-landsat)`
  removes ~26k bulk records). Fields: abstract, begindate, doi, enddate, funding,
  geographicdescription, id, methods, packageid, pubdate, responsibleParties, scope,
  singledate, site, taxonomic, title; multi-valued author, coordinates, keyword,
  organization, projectTitle, relatedProjectTitle, timescale.
- Feeds: `/changes/eml?fromDate=&toDate=&scope=`, `/uploads/eml?type=insert|update&limit=`.
- Audit: `https://pasta.lternet.edu/audit/reads/{scope}/{id}[/{rev}]`.
- Formats (verified 2026-10-17 with a key): search returns
  `<resultset numFound='…'><document><packageid/><title/><pubdate/><doi/><begindate/>
  <enddate/><scope/><keywords><keyword/></keywords><authors><author/></authors>`; the
  `doi` field matches `q=doi:"doi:10.6073/pasta/<md5>"` (quoted, with the `doi:` prefix)
  and covers newest revisions only. A missing package is 404 text/plain
  `Unable to access metadata for 'scope.id.rev'.`
- PASTA sets `Set-Cookie: edi-token=…` on responses, anonymous 403s included.
- Hosts: production `pasta.lternet.edu`, staging `pasta-s`, development `pasta-d`;
  portal `portal.edirepository.org/nis/mapbrowse?scope=&identifier=&revision=`.
- No published rate limits.

## 4. MCP 2026-07-28 and SDKs (verified 2026-10-17)

- Spec: https://modelcontextprotocol.io/specification/2026-07-28/changelog — sessions
  and `initialize` removed (per-request `_meta`), `server/discover` required,
  `resultType` on every result, `ttlMs`/`cacheScope` on list/read results, MRTR replaces
  server-initiated elicitation/sampling, Streamable HTTP is POST-only with
  `MCP-Protocol-Version`/`Mcp-Method`/`Mcp-Name` headers, tasks moved to an extension,
  roots/sampling/logging deprecated, Server Cards as an extension.
- Python `mcp` 2.3.0 (2026-10-02) supports 2026-07-28 and still serves 2025-era clients;
  `FastMCP` was renamed `MCPServer` in 2.x (we use the low-level `Server`, as neon-mcp does).

## 5. Search filters, scopes and access control (verified 2026-10-18)

Probed live with a profile key (PASTA) and anonymously (DataONE CN Solr).

- **Sort.** PASTA takes `sort=pubdate,desc` / `sort=pubdate,asc`; `sort=pubdate desc`
  (Solr's usual form) is accepted with HTTP 200 and **silently ignored**. DataONE takes
  `sort=pubDate desc|asc`. On both, ascending order lists packages without a publication
  date first.
- **Bounding box.** PASTA: `fq=coordinates:"Intersects(ENVELOPE(minX, maxX, maxY, minY))"`
  (west, east, north, south). A malformed shape is a **500** from PASTA's Solr ("Unable to
  parse shape"), so edi-mcp validates the box before sending it. DataONE:
  `northBoundCoord:[south TO *] AND southBoundCoord:[* TO north] AND
  eastBoundCoord:[west TO *] AND westBoundCoord:[* TO east]` (cannot cross the
  antimeridian). A Jornada box (-107, 32.4, -106.5, 32.8) returns mostly `knb-lter-jrn`
  on both once the bulk scopes are excluded.
- **Author.** PASTA `author:"likens"` is case-insensitive. DataONE `origin` is an exact,
  case-sensitive full name (`origin:"Gene E. Likens"`; `origin:Likens`, `origin:*Likens*`
  find nothing) and `authorLastName` is case-sensitive; `investigatorText:likens`
  (tokenized last names) is case-insensitive and is what edi-mcp uses.
- **Temporal.** PASTA `begindate`/`enddate` and DataONE `beginDate`/`endDate` take Solr
  date ranges; overlap with [start, end] is `begin <= end AND end >= start`.
- **Bulk scopes.** `lter-landsat-ledaps` (10 471 packages) is a third generated scope
  next to `ecotrends` (15 403) and `lter-landsat` (10 492); unexcluded, it floods
  spatial queries.
- **Scopes.** `/package/eml` lists 41 scopes; `resources_static/scopes.json` records
  them with package counts. DataONE does not replicate `cos-spu` or `icarus`. DataONE's
  per-scope counts exceed PASTA's (e.g. `knb-lter-jrn` 481 vs 224) because superseded
  revisions often lack `obsoletedBy` (D12). Scope names come from package titles and
  organizations: `knb-lter-nwk` is the LTER Network Office, `cos-spu` the City of Seattle,
  Seattle Public Utilities, `msb-paleon` PalEON (43 of 47 packages mention it). No name
  is verified for `icarus` (its one package is from the Mountain Ecology Research
  Institute), `msb-cap` or `msb-tempbiodev`.
- **Revision 0 exists** (`msb-paleon.31.0`).
- **Free text is safe to pass through.** Under `defType=edismax` both Solr instances
  answer 200 to unbalanced syntax (`"unbalanced`, `title:(foo`, `[1 TO`,
  `streamflow AND`, `soil)`, a lone backslash); none produced a 500. edi-mcp still drops
  a leading `{!…}` local-params block from the query text.
- **Access-restricted packages.** PASTA search lists `icarus.13.1`, but reading its
  metadata with a valid key returns **403** "User 'EDI-… (Display Name)' is not
  authorized to read '…'". A bad key or token gets 401, so a credentialed 403 means the
  package is restricted, not that the key is wrong. The 403 text carries the caller's
  display name; the client removes the whole `User '…'` quote from upstream error text.

## 6. Package reads, EML and DataONE drift (verified 2026-10-19)

- **DataONE changed its index between 2026-10-18 and 2026-10-19.**
  - `pubDate` and `datePublished` became range fields: `sort=pubDate desc` now fails with
    400 "Sorting not supported on SpatialField". `dateUploaded` still sorts, so edi-mcp sorts
    DataONE results by upload date and says so in `notes`.
  - About 15% of EDI/LTER metadata records (12 616 of 80 325) carry legacy ids registered
    by the old LTER node (`knb-lter-pie.454.1`) instead of PASTA URLs; filter-only queries
    now rank them first. edi-mcp parses both forms. Some carry malformed `pubDate`
    (`+20071203-01-01T…`), which is dropped.
  - `cos-spu` gained 7 DataONE records (0 the day before), and `knb-lter-hbr.14.22` is now
    indexed (its DOI comes from Solr, not the citation service). The scope snapshot stays
    dated; the "no replica" note is shown only when a DataONE search comes back empty.
  - Lesson: assertions about DataONE ranking are not stable. Live tests compare counts
    within one scope instead (Jornada box vs. its eastern-hemisphere mirror).
- **Anonymous data.** Both member nodes serve data entities without credentials:
  `gmn.lternet.edu/mn/v2/object/<url-encoded PASTA data URL>` (knb-lter-hbr.14.22) and
  `gmn.edirepository.org/mn/v2/object/…` (edi.2081.1). The CN `/object` returns 404 for data
  entities. GMN **ignores `Range`** (200, no `Content-Range`), so previews must stream and
  stop reading.
- **GMN serves EML DataONE has not indexed.** `knb-lter-jrn.210548103.33` (PASTA's newest)
  is missing from Solr (newest there: 32, and 3, 4, 29 and 30 are absent), yet its EML
  resolves on `gmn.lternet.edu` and its entity is listed without a SHA-1 (no index record).
- **EML at scale.** `knb-lter-mcr.6.65` is 3.4 MB (1 144 taxa, 4 tables of up to 26
  columns); it downloads in ~1.8 s and parses in 0.05 s with defusedxml, so projections are
  cheap and every list is capped with a total.
- **EML conventions seen.** `recordDelimiter` is written as the literal text `\r\n`;
  `physical/size` may carry `unit`; roles of referenced parties sit beside `<references>`
  (`<personnel><references>id</references><role>…</role>`); EML 2.1 uses free-text
  `funding`, EML 2.2 `award` and `licensed`.
- **Entity ids.** The MD5-of-`entityName` rule matched PASTA's `/name` list for every
  entity of `knb-lter-hbr.14.22` (5) and `knb-lter-jrn.210548103.32` (1).

## 7. Step-6 endpoints (verified 2026-10-19)

- **Quality reports are anonymous on GMN.** `gmn.lternet.edu/mn/v2/object/<url-encoded
  https://pasta.lternet.edu/package/report/eml/s/i/r>` and the same on
  `gmn.edirepository.org` (checked `knb-lter-hbr.14.22`, `edi.2081.1`) return the
  `qr:qualityReport` XML (`application/octet-stream`) without credentials, byte-identical
  to PASTA's. Structure: `creationDate`, `packageId`, `datasetReport/qualityCheck*`,
  `entityReport/{entityName, qualityCheck*}`; each check has `identifier`, `name`,
  `found`, `status` (valid, info, warn, error), `explanation`, `suggestion`. Sizes:
  hbr.14.22 83 KB (5 entities), jrn.210548103.32 32 KB, edi.2081.1 22 KB.
- **Lineage.** `/package/sources/eml/…` → `<dataSources><dataSource><packageId/><title/><url/>`;
  `/descendants/eml/…` → `<dataDescendants><dataDescendant>…`. Titles are escaped twice
  (`&#x26;&#x23;x3a&#x3b;` parses to `&#x3a;`), so `html.unescape` them. hbr.14.22's source
  is hbr.278.8, whose descendant is hbr.14.22.
- **Change feed.** `/package/changes/eml?fromDate=&toDate=&scope=` → `<dataPackageChanges>
  <dataPackage><packageId/><scope/><identifier/><revision/><principal>EDI-<40 hex></principal>
  <doi/><serviceMethod>createDataPackage|updateDataPackage|…</serviceMethod>
  <date>2026-10-12T22:19:37.455</date>`. `/uploads/eml` has the same shape with
  `2026-10-19 17:53:59` dates. Both name **other users' principals**: never surface them.
- **Read counts.** `/audit/reads/{s}/{i}[/{r}]` → `<resourceReads><resource><resourceId/>
  <resourceType>dataPackage|metadata|report|data|archive</resourceType><scope/><identifier/>
  <revision/><totalReads/><nonRobotReads/>`. Series-level for hbr.14 is 48 KB; edi.2081 1.8 KB.
- **Citations.** `cite.edirepository.org/cite/{packageId}?style=ESIP|DRYAD|BIBTEX` →
  text/plain; `Accept: application/json` → `{authors, pub_year, title, version, publisher,
  doi}` with trailing periods (`"2026."`, `"…b062."`). A missing **or** access-restricted
  package (`icarus.13.1`) is HTTP 400 with an HTML page.
- **Data.** PASTA `/package/data/eml/…/{entity}` streams the bytes (`text/csv` for
  thiessen_weights, 734 B); GMN adds `DataONE-Checksum: SHA-1,<hex>`.
  `/package/download/eml/{s}/{i}/{r}` is the whole package as `application/zip` with no
  `Content-Disposition`; edi.2081.1's is 779 MB, so the download tool caps every stream.
