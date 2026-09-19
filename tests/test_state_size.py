#!/usr/bin/env python3
"""TEST 3 + TEST 4 for the one server-side line the pinch needed.

MA Reader's server sanitises everything the browser sends, and it used to end
that pass with int(st["size"]). A pinch would then have worked perfectly on
the screen and been rounded back to a whole step by the next page load - the
silent failure, where the browser is told the write succeeded and the value
is quietly different. This proves the rounding is gone and the guard rails
that were around it are not.
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SH = (sys.argv[1] if len(sys.argv) > 1 else
      os.path.join(HERE, "..", "..", "MA_READER_TERMUX_MACOS",
                   "3sh_i_ma_reader_v3_termux.sh"))
if not os.path.exists(SH):
    print("  skipped: MA Reader's installer is not beside this repo.")
    print("           pass its path:  python3 tests/test_state_size.py <installer.sh>")
    sys.exit(0)
src = io.open(SH, encoding="utf-8").read()

# lift the real clamp out of the real installer, so this tests what ships
m = re.search(r"(    def _num\(key, lo, hi, default, nd=2\):.*?"
              r'\n    st\["volume"\] = int\(st\["volume"\]\)\n)', src, re.S)
if not m:
    sys.exit("could not find the clamp in the installer")
body = "\n".join(l[4:] if l.startswith("    ") else l
                 for l in m.group(1).split("\n"))

def clamp(st):
    ns = {"st": st}
    exec(body, ns)                 # noqa: S102 - the point is to run the real thing
    return st

fails = ran = 0
def ok(name, cond, extra=""):
    global fails, ran
    ran += 1
    print(("  pass  " if cond else "  FAIL  ") + name + ("   " + str(extra) if extra else ""))
    if not cond:
        fails += 1

BASE = {"lag": 0.0, "speed": 1.0, "volume": 100, "lineheight": 1.6}
def st(size):
    d = dict(BASE); d["size"] = size; return d

print("\n=== TEST 4  the upgrade, from the version before ===")
old = clamp(st(4))                 # what every existing state.json holds
ok("a whole size from the old version still loads", old["size"] == 4, old["size"])
ok("and is still a number the page can use", isinstance(old["size"], (int, float)))
ok("volume is still a whole number", isinstance(clamp(st(4))["volume"], int))

print("\n=== TEST 3  the ugly cases ===")
ok("a pinched size survives the round trip", clamp(st(7.35))["size"] == 7.35,
   clamp(st(7.35))["size"])
ok("more precision than a pinch needs is rounded, not refused",
   clamp(st(7.123456))["size"] == 7.12, clamp(st(7.123456))["size"])
ok("above the ceiling is pulled back to the ceiling",
   clamp(st(99.9))["size"] == 14, clamp(st(99.9))["size"])
ok("below the floor is pulled up to the floor",
   clamp(st(-3))["size"] == 1, clamp(st(-3))["size"])
ok("a string of a number is read as one", clamp(st("8.5"))["size"] == 8.5,
   clamp(st("8.5"))["size"])
ok("nonsense falls back to the default", clamp(st("banana"))["size"] == 2,
   clamp(st("banana"))["size"])
ok("null falls back to the default", clamp(st(None))["size"] == 2,
   clamp(st(None))["size"])
ok("a missing key falls back to the default", clamp(dict(BASE))["size"] == 2,
   clamp(dict(BASE))["size"])
ok("a list is not arithmetic", clamp(st([1, 2]))["size"] == 2,
   clamp(st([1, 2]))["size"])
ok("infinity does not become the ceiling by accident",
   clamp(st(float("inf")))["size"] == 14, clamp(st(float("inf")))["size"])
try:
    v = clamp(st(float("nan")))["size"]
    ok("NaN does not come back out as NaN", v == v, v)
except Exception as e:
    ok("NaN does not come back out as NaN", False, repr(e))
ok("saving twice changes nothing the second time",
   clamp(st(clamp(st(7.35))["size"]))["size"] == 7.35)

print("\n  " + ("%d FAILED of %d" % (fails, ran) if fails else "all %d passed" % ran) + "\n")
sys.exit(1 if fails else 0)
