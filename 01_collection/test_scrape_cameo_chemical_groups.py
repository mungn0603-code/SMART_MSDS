"""Assert-based self-check for scrape_cameo_chemical_groups.py. Run directly:
    python test_scrape_cameo_chemical_groups.py
"""

from scrape_cameo_chemical_groups import GROUP_LINK_RE, parse_result_page

SAMPLE_PAGE = """
<div class="result chemical-result">
    <a class="match_name" href="/chemical/19698">ABIETIC ACID</a>
<br />
    Yellowish resinous powder. <br />
<span class="match_label">CAS Number:</span>
514-10-3
<br />
<span class="match_label">UN/NA Number:</span>
none
<br />
</div>

<div class="result chemical-result">
    <a class="match_name" href="/chemical/99999">SOME MIXTURE</a>
<br />
    A mixture with no single CAS. <br />
<span class="match_label">CAS Number:</span>
none
<br />
</div>

Page <b>2</b> of <b>11</b>
"""

SAMPLE_GROUP_LIST = """
<a href="/react/70">Acetals, Ketals, Hemiacetals, and Hemiketals</a>
<a href="/react/3">Acids, Carboxylic</a>
"""


def test_parse_result_page():
    entries, total_pages = parse_result_page(SAMPLE_PAGE)
    assert entries == [
        (19698, "ABIETIC ACID", "514-10-3"),
        (99999, "SOME MIXTURE", None),
    ]
    assert total_pages == 11


def test_group_link_parsing():
    links = GROUP_LINK_RE.findall(SAMPLE_GROUP_LIST)
    assert links == [
        ("70", "Acetals, Ketals, Hemiacetals, and Hemiketals"),
        ("3", "Acids, Carboxylic"),
    ]


if __name__ == "__main__":
    test_parse_result_page()
    test_group_link_parsing()
    print("all tests passed")
