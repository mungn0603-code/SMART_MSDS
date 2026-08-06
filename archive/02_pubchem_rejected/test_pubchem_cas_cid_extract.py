"""Assert-based self-check for pubchem_cas_cid_extract.py. Run directly:
    python test_pubchem_cas_cid_extract.py
"""

import gzip
import io

from pubchem_cas_cid_extract import CAS_RE, iter_rows, iter_sdf_records, parse_record

RECORD_1 = """\
Compound1
     RDKit

  0  0  0  0  0  0  0  0  0  0999 V2000
M  END
> <PUBCHEM_COMPOUND_CID>
7

> <PUBCHEM_IUPAC_NAME>
acetic acid

> <PUBCHEM_SUBSTANCE_SYNONYM>
64-19-7
Acetic acid

"""

RECORD_2 = """\
Compound2
> <PUBCHEM_COMPOUND_CID>
702

> <PUBCHEM_IUPAC_NAME>
ethanol

> <PUBCHEM_SUBSTANCE_SYNONYM>
64-17-5
64-17-5

"""


def test_cas_regex():
    assert CAS_RE.findall("see 64-19-7 and 7732-18-5 and 50-00-0") == [
        "64-19-7", "7732-18-5", "50-00-0",
    ]
    assert CAS_RE.findall("not-a-cas 12345678-1-2") == []  # 8-digit prefix too long


def test_iter_sdf_records_splits_on_dollar_marker():
    raw = (RECORD_1 + "$$$$\n" + RECORD_2 + "$$$$\n").encode("utf-8")
    lines = io.BytesIO(raw).readlines()
    records = list(iter_sdf_records(lines))
    assert len(records) == 2
    assert "PUBCHEM_COMPOUND_CID" in records[0]
    assert "ethanol" in records[1]


def test_parse_record_extracts_cid_name_cas():
    cid, name, cas_numbers = parse_record(RECORD_1)
    assert cid == "7"
    assert name == "acetic acid"
    assert cas_numbers == {"64-19-7"}


def test_iter_rows_dedupes_across_records():
    raw = (RECORD_1 + "$$$$\n" + RECORD_2 + "$$$$\n").encode("utf-8")

    def fake_iter_sdf_records_from_url(url):
        yield from iter_sdf_records(io.BytesIO(raw).readlines())

    import pubchem_cas_cid_extract as mod
    mod.iter_sdf_records_from_url = fake_iter_sdf_records_from_url

    rows = list(iter_rows(["fake://one-file"]))
    assert rows == [("64-19-7", "7", "acetic acid"), ("64-17-5", "702", "ethanol")]


if __name__ == "__main__":
    test_cas_regex()
    test_iter_sdf_records_splits_on_dollar_marker()
    test_parse_record_extracts_cid_name_cas()
    test_iter_rows_dedupes_across_records()
    print("all tests passed")
