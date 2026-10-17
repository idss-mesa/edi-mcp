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
