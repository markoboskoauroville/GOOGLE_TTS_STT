#!/usr/bin/env python3
"""Lift the pinch code, and the whole page, out of whatever is shipping.

The reader page exists three times and always will — once as src/45_reader.html
here, and once inside each of MA Reader's two installers as a heredoc. Testing
a fourth, retyped copy would prove nothing about any of them, so everything
under tests/ reads the shipped file and nothing else.

    python3 tests/pinch_extract.py <file> --js      the pinch functions
    python3 tests/pinch_extract.py <file> --page    the whole HTML page

<file> is src/45_reader.html, or either 3sh_i_ma_reader_v3_*.sh.
"""
import io, re, sys

FIRST = "function sizeOf(v, dflt){"
LAST  = "function wirePinch(){"


def page(path):
    """The HTML, out of a .sh installer's heredoc if that is what this is."""
    s = io.open(path, encoding="utf-8").read()
    start = 'cat > "$APPDIR/static/index.html" << \'HTMLEOF\'\n'
    if start in s:
        i = s.index(start) + len(start)
        return s[i:s.index("\nHTMLEOF\n", i)]
    return s


def js(path):
    """sizeOf through the closing brace of wirePinch, verbatim."""
    s = page(path)
    a = s.index(FIRST)
    b = s.index(LAST, a)
    m = re.search(r"^}", s[b:], re.M)          # wirePinch's own closing brace
    if not m:
        sys.exit("wirePinch is not closed at the left margin")
    return s[a:b + m.end()]


if __name__ == "__main__":
    f = sys.argv[1]
    sys.stdout.write(js(f) if "--js" in sys.argv else page(f))
