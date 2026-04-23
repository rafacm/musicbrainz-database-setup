"""Test the regex parsing of the fullexport directory index."""

from musicbrainz_database_setup.mirror.index import DATED_DIR_RE

INDEX_HTML = """
<html><body>
<pre>
<a href="../">../</a>
<a href="20260408-002212/">20260408-002212/</a>  08-Apr-2026 00:22   -
<a href="20260405-002212/">20260405-002212/</a>  05-Apr-2026 00:22   -
<a href="LATEST">LATEST</a>
<a href="README">README</a>
</pre>
</body></html>
"""


def test_dated_dir_regex_extracts_all_dated_dirs():
    matches = DATED_DIR_RE.findall(INDEX_HTML)
    assert set(matches) == {"20260408-002212", "20260405-002212"}


def test_dated_dir_regex_does_not_match_latest_or_readme():
    assert "LATEST" not in DATED_DIR_RE.findall(INDEX_HTML)
    assert "README" not in DATED_DIR_RE.findall(INDEX_HTML)
