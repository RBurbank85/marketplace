from pathlib import Path
from collectors.parsers.craigslist import CraigslistParser


def test_craigslist_parser_with_fixture():
    fixture_path = Path(__file__).parent / "fixtures" / "craigslist_search.html"
    html = fixture_path.read_text(encoding="utf-8")

    parser = CraigslistParser()
    items = parser.parse(html)

    assert len(items) == 3

    assert items[0]["title"] == "Vintage Camera"
    assert items[0]["url"] == "https://sfbay.craigslist.org/sfc/ele/7700000001.html"
    assert items[0]["price"] == "$50"

    assert items[1]["title"] == "Modern Laptop"
    assert items[1]["url"] == "https://sfbay.craigslist.org/sfc/ele/7700000002.html"
    assert items[1]["price"] == "$500"

    assert items[2]["title"] == "Broken Toaster"
    assert items[2]["url"] == "https://sfbay.craigslist.org/sfc/ele/7700000003.html"
    assert items[2]["price"] == "$5"


def test_craigslist_parser_empty_html():
    parser = CraigslistParser()
    items = parser.parse("")
    assert items == []


def test_craigslist_parser_no_results():
    parser = CraigslistParser()
    items = parser.parse("<html><body><p>No results found</p></body></html>")
    assert items == []


def test_craigslist_parser_current_layout():
    """Parser handles the current Craigslist layout where the title is a
    <div class="title"> inside a parent <a> tag, and listing URLs use
    alphanumeric IDs instead of numeric ones."""
    html = """
    <ol class="cl-static-search-results">
        <li class="cl-static-search-result" title="Sony Receiver">
            <a href="https://www.craigslist.org/view/d/denver-sony-receiver/exUqi1zx1Wtjx1Amj7uYnK">
                <div class="title">Sony Receiver</div>
                <div class="details">
                    <div class="price">$60</div>
                    <div class="location">LAKEWOOD</div>
                </div>
            </a>
        </li>
        <li class="cl-static-search-result" title="Denon Amplifier">
            <a href="https://www.craigslist.org/view/d/denver-denon-amplifier/cnMpNnYoGQXeQ6yucDegs1">
                <div class="title">Denon Amplifier</div>
                <div class="details">
                    <div class="price">$100</div>
                </div>
            </a>
        </li>
    </ol>
    """
    parser = CraigslistParser()
    items = parser.parse(html)

    assert len(items) == 2

    assert items[0]["title"] == "Sony Receiver"
    assert items[0]["url"] == "https://www.craigslist.org/view/d/denver-sony-receiver/exUqi1zx1Wtjx1Amj7uYnK"
    assert items[0]["price"] == "$60"
    assert items[0]["external_id"] == "exUqi1zx1Wtjx1Amj7uYnK"

    assert items[1]["title"] == "Denon Amplifier"
    assert items[1]["url"] == "https://www.craigslist.org/view/d/denver-denon-amplifier/cnMpNnYoGQXeQ6yucDegs1"
    assert items[1]["price"] == "$100"
    assert items[1]["external_id"] == "cnMpNnYoGQXeQ6yucDegs1"
