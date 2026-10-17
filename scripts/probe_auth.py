"""Probe which credential forms PASTA accepts for read calls (plan Step 1).

Since 2026-07-30 PASTA rejects anonymous requests with 403 "Public Access ... not
authorized". This script checks, with a real EDI API key, which of these work:

  A. key -> edi-token exchange (POST auth.edirepository.org/auth/v1/key), sent as
     ``Cookie: edi-token=<JWT>``
  B. ``?key=<API key>`` query parameter
  C. no credentials (baseline; expected 403)

and whether the token refresh endpoint works. Results go to stdout and, with
``--json PATH``, to a JSON file for RESEARCH.md. The key and token are never printed:
URLs are scrubbed and response bodies are truncated and scrubbed.

Usage:
    EDI_API_KEY=... python3 scripts/probe_auth.py [--json probe.json]

Stdlib only, so it runs before ``uv sync``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

PASTA = "https://pasta.lternet.edu"
AUTH = "https://auth.edirepository.org/auth/v1"
UA = "edi-mcp-probe/0.1 (+https://github.com/idss-mesa/edi-mcp)"
TIMEOUT = 30

# Verified-existing package (DataONE GMN served its data entity on 2026-10-17).
SCOPE, IDENT, REV = "knb-lter-hbr", "14", "22"
ENTITY = "c4f72fa0cb155f1b61f1333bb67e3d00"
_week_ago = (date.today() - timedelta(days=7)).isoformat()

CALLS: list[tuple[str, str]] = [
    ("listDataPackageScopes", "/package/eml"),
    ("listDataPackageIdentifiers", f"/package/eml/{SCOPE}"),
    ("listDataPackageRevisions", f"/package/eml/{SCOPE}/{IDENT}?filter=newest"),
    ("readDataPackage", f"/package/eml/{SCOPE}/{IDENT}/{REV}"),
    ("readMetadata", f"/package/metadata/eml/{SCOPE}/{IDENT}/{REV}"),
    ("readDataEntityNames", f"/package/name/eml/{SCOPE}/{IDENT}/{REV}"),
    ("readDataEntitySizes", f"/package/data/size/eml/{SCOPE}/{IDENT}/{REV}"),
    ("readDataEntityChecksum", f"/package/data/checksum/eml/{SCOPE}/{IDENT}/{REV}/{ENTITY}"),
    ("readDataPackageDoi", f"/package/doi/eml/{SCOPE}/{IDENT}/{REV}"),
    ("readDataPackageReport", f"/package/report/eml/{SCOPE}/{IDENT}/{REV}"),
    ("readDataSources", f"/package/sources/eml/{SCOPE}/{IDENT}/{REV}"),
    ("searchDataPackages", "/package/search/eml?defType=edismax&q=streamflow&fl=packageid,title,doi&rows=2"),
    ("listDataChanges", f"/package/changes/eml?fromDate={_week_ago}&scope={SCOPE}"),
    ("listRecentUploads", "/package/uploads/eml?type=insert&limit=2"),
    ("getReadCounts", f"/audit/reads/{SCOPE}/{IDENT}"),
]


class Secrets:
    """Holds the values that must never reach output, and scrubs them from text."""

    def __init__(self) -> None:
        self.values: list[str] = []

    def add(self, value: str | None) -> None:
        if value:
            self.values.append(value)
            self.values.append(urllib.parse.quote(value, safe=""))

    def scrub(self, text: str) -> str:
        for v in self.values:
            text = text.replace(v, "<redacted>")
        return text


SECRETS = Secrets()


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    range_bytes: int | None = 2048,
) -> dict[str, Any]:
    hdrs = {"User-Agent": UA, **(headers or {})}
    if range_bytes and method == "GET":
        hdrs["Range"] = f"bytes=0-{range_bytes - 1}"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
            status, ctype = resp.status, resp.headers.get("Content-Type", "")
            raw = resp.read(4096)
    except urllib.error.HTTPError as e:
        status, ctype = e.code, e.headers.get("Content-Type", "")
        raw = e.read(4096)
    except (urllib.error.URLError, TimeoutError) as e:
        return {"status": None, "error": SECRETS.scrub(str(e))}
    text = raw.decode("utf-8", errors="replace")
    return {"status": status, "contentType": ctype, "bodyHead": SECRETS.scrub(text[:200]), "_raw": text}


def jwt_lifetime(token: str) -> int | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return int(claims["exp"]) - int(claims["iat"])
    except (IndexError, KeyError, ValueError):
        return None


def exchange_key(key: str) -> tuple[str | None, dict[str, Any]]:
    r = request(
        f"{AUTH}/key",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        body=json.dumps({"key": key}).encode(),
        range_bytes=None,
    )
    token = None
    if r.get("status") == 200:
        try:
            token = json.loads(r["_raw"]).get("edi-token")
        except ValueError:
            pass
    SECRETS.add(token)
    r["bodyHead"] = SECRETS.scrub(r.get("bodyHead", ""))
    r["gotToken"] = bool(token)
    r["tokenLifetimeSeconds"] = jwt_lifetime(token) if token else None
    return token, r


def refresh(token: str) -> dict[str, Any]:
    r = request(
        f"{AUTH}/token/refresh",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        body=json.dumps({"edi-token": token}).encode(),
        range_bytes=None,
    )
    new = None
    if r.get("status") == 200:
        try:
            new = json.loads(r["_raw"]).get("edi-token")
        except ValueError:
            pass
    SECRETS.add(new)
    r["bodyHead"] = SECRETS.scrub(r.get("bodyHead", ""))
    r["gotToken"] = bool(new)
    return r


def with_key(path: str, key: str) -> str:
    return f"{PASTA}{path}{'&' if '?' in path else '?'}key={urllib.parse.quote(key, safe='')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", help="write results to this JSON file")
    args = ap.parse_args()

    key = os.environ.get("EDI_API_KEY", "").strip()
    if not key:
        print("EDI_API_KEY is not set; create one at https://auth.edirepository.org (Profile -> API keys).")
        return 2
    SECRETS.add(key)

    token, exch = exchange_key(key)
    results: dict[str, Any] = {"date": date.today().isoformat(), "exchange": exch, "calls": {}}
    if token:
        results["refresh"] = refresh(token)

    modes = {"anonymous": None, "cookie": token, "queryKey": key}
    for name, path in CALLS:
        row: dict[str, Any] = {"path": path}
        for mode, cred in modes.items():
            if mode == "cookie" and not cred:
                row[mode] = {"status": None, "error": "no token from exchange"}
                continue
            if mode == "queryKey":
                url, hdrs = with_key(path, key), {}
            elif mode == "cookie":
                url, hdrs = f"{PASTA}{path}", {"Cookie": f"edi-token={cred}"}
            else:
                url, hdrs = f"{PASTA}{path}", {}
            row[mode] = request(url, headers=hdrs)
        results["calls"][name] = row

    def strip(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k != "_raw"}
        return o

    clean = strip(results)
    print(f"key->token exchange: HTTP {exch.get('status')}  token={exch['gotToken']}  "
          f"lifetime={exch.get('tokenLifetimeSeconds')}s")
    if "refresh" in clean:
        print(f"token refresh:       HTTP {clean['refresh'].get('status')}  token={clean['refresh']['gotToken']}")
    print(f"\n{'service method':30} {'anon':>5} {'cookie':>7} {'?key=':>6}")
    for name, row in clean["calls"].items():
        print(f"{name:30} {row['anonymous'].get('status')!s:>5} {row['cookie'].get('status')!s:>7} "
              f"{row['queryKey'].get('status')!s:>6}")

    out = json.dumps(clean, indent=2)
    if any(v in out for v in SECRETS.values):  # belt and braces
        print("refusing to write results: a secret survived scrubbing", file=sys.stderr)
        return 1
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(out + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
