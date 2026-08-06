#!/usr/bin/env python3
"""Stream PubChem Compound Full SDF files (.sdf.gz) and extract a
CAS_Number|PubChem_CID|Systematic_Name mapping CSV without loading
whole files or the full result set into memory.

Usage:
    python pubchem_cas_cid_extract.py [output.csv]
"""

import csv
import gzip
import re
import sys
import urllib.request

FTP_INDEX = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/"
CAS_RE = re.compile(r'\b\d{2,7}-\d{2}-\d\b')
TAG_RE = re.compile(r'^>\s*<(\S+)>')


def list_sdf_urls(index_url=FTP_INDEX):
    """Scrape the directory listing page for .sdf.gz file links."""
    with urllib.request.urlopen(index_url) as resp:
        html = resp.read().decode("utf-8", "ignore")
    names = sorted(set(re.findall(r'href="([^"]+\.sdf\.gz)"', html)))
    return [index_url + name for name in names]


def iter_sdf_records(fileobj):
    """Yield one raw SDF record (text) at a time from an already-open,
    gzip-decompressing binary stream. Records are separated by a
    line starting with '$$$$', per the SDF spec."""
    buf = []
    for raw in fileobj:
        line = raw.decode("utf-8", "ignore")
        if line.startswith("$$$$"):
            yield "".join(buf)
            buf = []
        else:
            buf.append(line)
    if buf:
        yield "".join(buf)


def iter_sdf_records_from_url(url):
    with urllib.request.urlopen(url) as resp, gzip.GzipFile(fileobj=resp) as gz:
        yield from iter_sdf_records(gz)


def parse_record(text):
    """Pull CID, IUPAC name, and every CAS number found anywhere in
    the record (tag not assumed, since CAS may live in Synonyms or
    other vendor-specific tags)."""
    cid = None
    name = ""
    tag = None
    for line in text.splitlines():
        m = TAG_RE.match(line)
        if m:
            tag = m.group(1)
            continue
        if not line.strip():
            continue
        if tag == "PUBCHEM_COMPOUND_CID" and cid is None:
            cid = line.strip()
        elif tag == "PUBCHEM_IUPAC_NAME" and not name:
            name = line.strip()
    return cid, name, set(CAS_RE.findall(text))


def iter_rows(urls):
    """Yield deduplicated (CAS, CID, Name) rows across all given SDF URLs."""
    # ponytail: dedup set holds every (cas, cid) pair seen so far in memory,
    # not full records. Fine to tens of millions of rows; move to an on-disk
    # set (e.g. sqlite) if that ceiling is ever hit.
    seen = set()
    for url in urls:
        for record in iter_sdf_records_from_url(url):
            cid, name, cas_numbers = parse_record(record)
            if not cid:
                continue
            for cas in cas_numbers:
                key = (cas, cid)
                if key in seen:
                    continue
                seen.add(key)
                yield cas, cid, name


def build_csv(out_path, urls=None, chunk_size=5000):
    """Write CAS_Number|PubChem_CID|Systematic_Name rows in chunks so
    only one chunk of rows is buffered at a time."""
    urls = urls if urls is not None else list_sdf_urls()
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="|")
        writer.writerow(["CAS_Number", "PubChem_CID", "Systematic_Name"])
        chunk = []
        for row in iter_rows(urls):
            chunk.append(row)
            if len(chunk) >= chunk_size:
                writer.writerows(chunk)
                chunk = []
        if chunk:
            writer.writerows(chunk)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "pubchem_cas_cid_map.csv"
    build_csv(out)
