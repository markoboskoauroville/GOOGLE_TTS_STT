#!/usr/bin/env python3
"""
TEST 1b — THE PARSER, ALONE

The file picker's whole promise is "give it any file and it will not break and
it will not duplicate". This is where that is proved, with no server, no keys
and no network.

Two halves are tested separately on purpose: FINDING a key must never be wrong,
NAMING it is allowed to be. A test that insists on a particular label for a
messy file would fail for a reason nobody should care about.
"""

import importlib.util, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp()
os.environ["HOME"] = HOME
KEYS = os.path.join(HOME, "ring.txt")
os.environ["GEMINI_KEYS"] = KEYS

spec = importlib.util.spec_from_file_location("app", os.path.join(ROOT, "src", "10_app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
app.KEYFILE = KEYS
app.HOME = os.path.join(HOME, ".google_tts_stt")

A = "AQ.Ab8RN6" + "A" * 24
B = "AQ.Ab8RN6" + "B" * 24
C = "AIzaSy" + "C" * 33
D = "AQ.Ab8RN6" + "D" * 24

CHECKS = 0
fails = []


def check(name, got, want=True):
    global CHECKS
    CHECKS += 1
    if got == want:
        print("   ok   %s" % name)
    else:
        print("   FAIL %s\n        got %r, want %r" % (name, got, want))
        fails.append(name)


def keys_in(text):
    return [k for _, k in app.parse_keys(text)[0]]


def labels_in(text):
    return [l for l, _ in app.parse_keys(text)[0]]


def reset():
    open(KEYS, "w").close()


print("TEST 1b — the parser, on any file")

# --------------------------------------------------------- FINDING the keys
# One row per shape a key file has actually arrived in.
shapes = {
    "the plain ring, label above key": "tribal\n%s\n\nsvaram\n%s\n" % (A, B),
    "a bare list, no labels at all": "%s\n%s\n" % (A, B),
    "everything on one line": "%s %s" % (A, B),
    "dotenv": "GEMINI_KEY_TRIBAL=%s\nGEMINI_KEY_SVARAM=%s\n" % (A, B),
    "json object": json.dumps({"tribal": A, "svaram": B}),
    "json nested in a list": json.dumps({"accounts": [{"name": "tribal", "key": A},
                                                      {"name": "svaram", "key": B}]}),
    "csv with a header": "account,key\ntribal,%s\nsvaram,%s\n" % (A, B),
    "csv the other way round": "key,account\n%s,tribal\n%s,svaram\n" % (A, B),
    "markdown table": "| account | key |\n|---|---|\n| tribal | %s |\n| svaram | %s |\n" % (A, B),
    "yaml": "tribal: %s\nsvaram: %s\n" % (A, B),
    "a note written by hand": "ok so tribal is %s\nand svaram is %s, don't lose these\n" % (A, B),
    "quoted and comma'd": '"tribal": "%s",\n"svaram": "%s",\n' % (A, B),
    "windows line endings": "tribal\r\n%s\r\n\r\nsvaram\r\n%s\r\n" % (A, B),
    "no trailing newline": "tribal\n%s\n\nsvaram\n%s" % (A, B),
    "keys inside a code fence": "```\ntribal\n%s\n\nsvaram\n%s\n```\n" % (A, B),
    "html": "<td>tribal</td><td>%s</td><td>svaram</td><td>%s</td>" % (A, B),
    "surrounded by prose and urls": (
        "See https://aistudio.google.com/apikey for tribal %s\n"
        "and the other one, svaram, is %s\n" % (A, B)),
}
for name, text in shapes.items():
    check("finds both keys: %s" % name, keys_in(text), [A, B])

check("finds an AIza key next to an AQ. key", keys_in("a\n%s\nb\n%s\n" % (A, C)), [A, C])
check("a key repeated in one file is one key", keys_in("%s\n%s\n%s\n" % (A, A, A)), [A])
check("order of appearance is kept", keys_in("%s\n%s\n%s\n" % (B, A, C)), [B, A, C])

# ---------------------------------------------------- NOT finding non-keys
junk = {
    "an empty file": "",
    "whitespace only": "   \n\n\t\n",
    "prose with no keys": "the arm is always yours, the permission is mine",
    "a git sha": "commit 3f2a1b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a",
    "base64 with padding": "aGVsbG8gdGhlcmUgdGhpcyBpcyBub3QgYSBrZXkgYXQgYWxs==",
    "a url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash",
    "a too-short lookalike": "AQ.Ab8RN6short",
    "the word AIza on its own": "AIza",
}
for name, text in junk.items():
    check("finds nothing in %s" % name, keys_in(text), [])

# binary, and a file that is simply not text
png = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40
check("a PNG does not raise", app.parse_keys(png)[0], [])
check("a PNG with a key hidden in it still gives the key",
      [k for _, k in app.parse_keys(png + A.encode())[0]], [A])

# --------------------------------------------------------------- ENORMOUS
big = ("filler line that is not a key\n" * 40000) + "tribal\n" + A + "\n"
check("a megabyte of noise with one key in it", keys_in(big), [A])

# ------------------------------------------------------------- the LABELS
check("label above the key", labels_in("tribal\n%s\n" % A), ["tribal"])
check("label before the key on the line", labels_in("tribal: %s\n" % A), ["tribal"])
check("label after the key on the line", labels_in("%s,tribal\n" % A), ["tribal"])
check("dotenv name, with the noise words stripped off",
      labels_in("GEMINI_API_KEY_TRIBAL=%s\n" % A), ["TRIBAL"])
check("json names win over the line above",
      labels_in(json.dumps({"tribal": A})), ["tribal"])
check("json records where the name is a sibling field",
      labels_in(json.dumps({"accounts": [{"name": "tribal", "key": A},
                                         {"name": "svaram", "key": B}]})),
      ["tribal", "svaram"])
check("json with label and apiKey",
      labels_in(json.dumps([{"label": "kukljica", "apiKey": A}])), ["kukljica"])
check("a fragment of json is never used as a label",
      any("{" in l or '"' in l for l in
          labels_in(json.dumps({"accounts": [{"name": "t", "key": A}]}))), False)
check("a markdown table cell", labels_in("| tribal | %s |\n" % A), ["tribal"])
check("no label anywhere leaves the label empty at the parsing stage",
      labels_in("%s\n" % A), [""])
check("a key is never used as the label of the key below it",
      labels_in("%s\n%s\n" % (A, B)), ["", ""])
reset()
r0 = app.import_keys("%s\n%s\n" % (A, B), "no labels.txt")
check("and importing them names them account 1, account 2",
      [a["label"] for a in r0["added"]], ["account 1", "account 2"])
reset()
check("a comment line is not taken as a label",
      labels_in("# put your keys below\n\n%s\n" % A), [""])
check("but a real label under a comment still works",
      labels_in("# my keys\n\ntribal\n%s\n" % A), ["tribal"])

# ------------------------------------------------ MERGING, and never twice
reset()
r = app.import_keys("tribal\n%s\n\nsvaram\n%s\n" % (A, B), "first.txt")
check("first import adds both", len(r["added"]), 2)
check("the ring holds two", r["ring"], 2)
check("nothing was reported as a duplicate", r["duplicates"], [])

r = app.import_keys("tribal\n%s\n\nsvaram\n%s\n" % (A, B), "the same file again.txt")
check("importing the same file again adds nothing", r["added"], [])
check("and reports both as already there", len(r["duplicates"]), 2)
check("the ring is still two", r["ring"], 2)
check("the file was not even rewritten", open(KEYS).read().count(A), 1)

r = app.import_keys("tribal\n%s\n\nkukljica\n%s\n" % (A, D), "overlapping.txt")
check("an overlapping file adds only what is new", [a["label"] for a in r["added"]], ["kukljica"])
check("and skips the one already held", len(r["duplicates"]), 1)
check("the ring is three", r["ring"], 3)
check("no key appears twice in the file", open(KEYS).read().count(A), 1)

# the same key under a different name is still the same key
r = app.import_keys("A DIFFERENT NAME\n%s\n" % A, "renamed.txt")
check("the same key with a new label is not imported again", r["added"], [])
check("the label already in the ring is the one kept",
      [l for l, k in app.load_ring() if k == A], ["tribal"])

# two different keys wanting the same name
r = app.import_keys("tribal\n%s\n" % ("AQ.Ab8RN6" + "E" * 24), "clash.txt")
check("a clashing label is numbered, not overwritten", r["added"][0]["label"], "tribal 2")
check("and the original keeps its name",
      len([l for l, _ in app.load_ring() if l == "tribal"]), 1)

# comments and hand edits in the ring survive an import
reset()
open(KEYS, "w").write("# my own note at the top\n\ntribal\n%s\n" % A)
app.import_keys("svaram\n%s\n" % B, "add one.txt")
check("a comment already in the ring survives", "# my own note at the top" in open(KEYS).read())
check("and the ring parses to two", len(app.load_ring()), 2)
check("the file is 600", oct(os.stat(KEYS).st_mode)[-3:], "600")

# an import that finds nothing changes nothing
before = open(KEYS).read()
r = app.import_keys("there are no keys in this sentence", "empty.txt")
check("a file with no keys adds nothing", r["added"], [])
check("and does not touch the ring", open(KEYS).read(), before)

# ------------------------------------------------------- a future format
maybe = "tribal\nZZ9_" + "x" * 40 + "\n"
pairs, maybes = app.parse_keys(maybe)
check("an unknown long token is not imported as a key", pairs, [])
check("but it is reported rather than silently dropped", len(maybes), 1)

# ------------------------------------------------------------ the receipt
files = os.listdir(os.path.join(app.HOME, "imports"))
check("a receipt was written", len(files) > 0)
body = open(os.path.join(app.HOME, "imports", sorted(files)[-1])).read()
check("and no whole key is in it", A not in body and B not in body)
check("but it says what happened", "added" in body)

print("\nTEST 1b: %d checks, %d failed" % (CHECKS, len(fails)))
sys.exit(1 if fails else 0)
