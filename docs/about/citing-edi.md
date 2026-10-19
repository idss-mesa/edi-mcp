---
title: "Citing EDI data"
description: "How to cite an EDI data package by its revision DOI (doi:10.6073/pasta/…), the ESIP, DRYAD and BibTeX styles of cite.edirepository.org, intellectual rights per package, and how to mention edi-mcp."
type: Policy
tags:
  - about
  - citation
  - DOI
  - data-policy
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: edi-policy
    resource: "https://edirepository.org/about/edi-policy"
    title: "EDI Policy — Data policy (version 2.0, updated 2026-04-01)"
    author: "team:edi"
  - id: edi-cite
    resource: "https://cite.edirepository.org/cite/knb-lter-hbr.14.22?style=ESIP"
    title: "EDI citation service (example: knb-lter-hbr.14.22)"
    author: "team:edi"
  - id: edi-mcp-license
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/LICENSE"
    title: "edi-mcp LICENSE file (MIT)"
    author: "team:idss-mesa"
status: stable
stale_after: "2027-04-19T00:00:00Z"
---

# Citing EDI data

edi-mcp is only a conduit. The data packages it finds belong to their creators and are
published by the Environmental Data Initiative (EDI). The intellectual rights stated in
each package, together with EDI's data policy[^edi-policy], govern how you may use and
credit them; this project's license does not.

## What to cite: one revision, one DOI

An EDI data package is identified as `scope.identifier.revision`, for example
`knb-lter-hbr.14.22` (scope `knb-lter-hbr`, the Hubbard Brook LTER; identifier `14`;
revision `22`). Published revisions are immutable: changes to a package appear as a new
revision, and each revision has its own DOI of the form `doi:10.6073/pasta/<md5>`.
Cite the revision you actually used, by its DOI, so that others get the same data.
[Package identifiers](../tools/identifiers.md) explains the formats edi-mcp accepts.

## Citation styles

EDI's citation service, `cite.edirepository.org`, formats a citation for any public
package without a key[^edi-cite]. It offers the ESIP, DRYAD and BIBTEX styles, and JSON
fields with `Accept: application/json`. For `knb-lter-hbr.14.22` on 2026-10-19:

=== "ESIP"

    > USDA Forest Service, Northern Research Station. 2026. Hubbard Brook Experimental
    > Forest: Total Daily Precipitation by Watershed, 1956 - ongoing ver 22.
    > Environmental Data Initiative.
    > https://doi.org/10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062.

=== "DRYAD"

    > USDA Forest Service, Northern Research Station (2026) Hubbard Brook Experimental
    > Forest: Total Daily Precipitation by Watershed, 1956 - ongoing. Environmental Data
    > Initiative. https://doi.org/10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062

=== "BIBTEX"

    ```bibtex
    @misc{knb-lter-hbr.14.22,
        author={USDA Forest Service, Northern Research Station},
        title={{Hubbard Brook Experimental Forest: Total Daily Precipitation by Watershed, 1956 - ongoing. ver 22}},
        year={2026},
        publisher={Environmental Data Initiative},
        doi={10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062},
        url={https://doi.org/10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062},
        note = {Type: dataset}
    }
    ```

You can request these yourself, for example
`https://cite.edirepository.org/cite/knb-lter-hbr.14.22?style=ESIP`. The EDI Data
Portal's landing page for each package shows the same citation.

!!! tip "Ask edi-mcp for the citation"

    [`edi_get_citation`](../tools/reference.md#edi_get_citation) returns these styles
    (`ESIP`, `DRYAD`, `BIBTEX`) and the citation's parts, including the DOI, from the
    same service and without a key; see
    [Citations, quality reports and lineage](../tools/citation-and-quality.md).

## Intellectual rights

EDI curates each package with the intellectual rights its provider declared in the EML
metadata. EDI advocates open access without use restrictions but allows providers to
declare more restrictive licenses. When a provider declares none, EDI adds a default
statement based on the Creative Commons CC0 1.0 "No Rights Reserved" waiver, which also
asks for attribution as professional etiquette[^edi-policy]. Check the rights stated in
the package you use rather than assuming a license; some packages are also
access-restricted and need permission from their contacts.

## About edi-mcp itself

If you retrieved data through edi-mcp you may mention the tool in your methods, but the
citation of record is always the data package DOI. Never cite PASTA or DataONE download
URLs. The edi-mcp server software is MIT-licensed by The Regents of the University of
New Mexico[^edi-mcp-license] and is not affiliated with or endorsed by EDI, the LTER
Network or DataONE. See [License](license.md).

[^edi-policy]: EDI Policy — Data policy, version 2.0 (updated 2026-04-01). <https://edirepository.org/about/edi-policy>
[^edi-cite]: EDI citation service. <https://cite.edirepository.org/cite/knb-lter-hbr.14.22?style=ESIP>
[^edi-mcp-license]: edi-mcp `LICENSE` file. <https://github.com/idss-mesa/edi-mcp/blob/main/LICENSE>
