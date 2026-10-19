---
title: "License"
description: "The edi-mcp server code is MIT-licensed by The Regents of the University of New Mexico; this documentation is CC-BY 4.0; EDI data packages carry their own intellectual rights, per package."
type: Policy
tags:
  - about
  - license
  - MIT
  - CC-BY
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: edi-mcp-license
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/LICENSE"
    title: "edi-mcp LICENSE file (MIT)"
    author: "team:idss-mesa"
  - id: mit
    resource: "https://opensource.org/license/mit"
    title: "The MIT License"
    author: "team:opensource-org"
  - id: cc-by-4
    resource: "https://creativecommons.org/licenses/by/4.0/"
    title: "Creative Commons Attribution 4.0 International (CC BY 4.0)"
    author: "team:creativecommons"
  - id: edi-policy
    resource: "https://edirepository.org/about/edi-policy"
    title: "EDI Policy — Data policy"
    author: "team:edi"
status: stable
---

# License

Three things meet on this site: the server software, the documentation you are
reading, and the EDI data packages the server gives access to. Each has its own license.

## Server code — MIT

The edi-mcp source code (the `edi_mcp` Python package, the `edi-mcp` command-line
program, tests and build scripts) is released under the
[MIT License](https://opensource.org/license/mit){target=_blank}[^mit]:

> Copyright (c) 2026 The Regents of the University of New Mexico

The full text is in the repository's
[`LICENSE`](https://github.com/idss-mesa/edi-mcp/blob/main/LICENSE){target=_blank}
file[^edi-mcp-license]. In short: you may use, copy, modify, merge, publish, distribute,
sublicense and sell the software, provided the copyright notice and permission notice
are included; the software is provided "as is", without warranty.

## Documentation text — CC-BY 4.0

The prose, tables and examples on this site (everything under `docs/` in the
repository, including the OKF frontmatter) are licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/){target=_blank}[^cc-by-4].
You may share and adapt the material for any purpose, provided you give appropriate
credit ("edi-mcp documentation, idss-mesa / The Regents of the University of New
Mexico, CC-BY 4.0") and indicate whether changes were made. Code snippets embedded in
the documentation may alternatively be used under the MIT terms above.

## EDI data — per package

Data packages retrieved from EDI through edi-mcp are not part of this project and are
not covered by either license above. Each package states its own intellectual rights in
its EML metadata. EDI advocates open access but lets providers declare more restrictive
terms; when a provider declares none, EDI applies a default statement based on the
CC0 1.0 waiver[^edi-policy]. Read the rights of each package you use, and cite it as
described in [Citing EDI data](citing-edi.md).

## Trademarks and affiliation

edi-mcp is an independent project of
[idss-mesa](https://github.com/idss-mesa){target=_blank} at the University of New
Mexico. It is not developed, endorsed or supported by the Environmental Data
Initiative, the LTER Network, DataONE or the U.S. National Science Foundation. Their
names belong to their respective owners; this site uses its own original artwork.

[^mit]: The MIT License. <https://opensource.org/license/mit>
[^edi-mcp-license]: edi-mcp `LICENSE` file. <https://github.com/idss-mesa/edi-mcp/blob/main/LICENSE>
[^cc-by-4]: Creative Commons Attribution 4.0 International. <https://creativecommons.org/licenses/by/4.0/>
[^edi-policy]: EDI Policy — Data policy. <https://edirepository.org/about/edi-policy>
