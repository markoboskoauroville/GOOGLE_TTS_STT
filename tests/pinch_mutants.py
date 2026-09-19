#!/usr/bin/env python3
"""Test the test. A green suite against a broken mechanism is worse than no
suite at all, because it is believed.

Each break below is planted in the shipped code, one at a time, and the suite
must go red. Nothing is written to the repository: the mutant goes to a temp
file and the tests are pointed at it.

    python3 tests/pinch_mutants.py [file]

Four of these got through on the first run, and the four tests that let them
through were rewritten. That is what this is for.
"""
import io, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "src", "45_reader.html")

good = subprocess.run([sys.executable, os.path.join(HERE, "pinch_extract.py"),
                       TARGET, "--js"], capture_output=True, text=True, check=True).stdout

MUTANTS = [
 ("the clamp is removed",
  "ST.size = Math.max(SIZE_MIN, Math.min(SIZE_MAX, size));",
  "ST.size = size;"),
 ("the NaN guard is removed",
  "if(!(size === size)) return;", "if(false) return;"),
 ("the divide-by-zero guard is removed",
  "return Math.sqrt(dx*dx + dy*dy) || 1;", "return Math.sqrt(dx*dx + dy*dy);"),
 ("the ratio is measured frame to frame",
  "const fs0 = 13 + PINCH.size0*2;", "const fs0 = 13 + ST.size*2;"),
 ("the place is not kept",
  "  pinchKeepPlace();\n  pinchShow();", "  pinchShow();"),
 ("the detached anchor is not noticed",
  "if(el.isConnected === false){ PINCH.anchor = null; return; }", ""),
 ("the click guard is removed",
  "PINCH.guard  = Date.now() + 400;", "PINCH.guard  = 0;"),
 ("the editor is not excluded",
  'if(document.body.classList.contains("mode-edit")) return;', ""),
 ("preventDefault is dropped",
  "if(e.cancelable) e.preventDefault();\n    /* The ratio", "/* The ratio"),
 ("the frame is thrown away instead of spent",
  "cancelAnimationFrame(PINCH.raf); PINCH.raf = 0;\n      pinchApply(PINCH.pending);",
  "cancelAnimationFrame(PINCH.raf); PINCH.raf = 0;"),
 ("two fingers anywhere are claimed",
  'if(!sc) return;\n    /* Editing the Markdown', '/* Editing the Markdown'),
 ("the NaN test in sizeOf is written the wrong way",
  "return (n === n) ? Math.max(SIZE_MIN, Math.min(SIZE_MAX, n)) : dflt;",
  "return (n !== undefined) ? Math.max(SIZE_MIN, Math.min(SIZE_MAX, n)) : dflt;"),
 ("sizeOf does not clamp",
  "return (n === n) ? Math.max(SIZE_MIN, Math.min(SIZE_MAX, n)) : dflt;",
  "return (n === n) ? n : dflt;"),
 ("a third finger is treated as two",
  "if(!PINCH.live || e.touches.length !== 2) return;", "if(!PINCH.live) return;"),
]

print("\n  planting %d breaks in %s\n" % (len(MUTANTS), os.path.basename(TARGET)))
bad = 0
tmp = os.path.join(tempfile.mkdtemp(), "mutant.js")
for name, old, new in MUTANTS:
    n = good.count(old)
    if n != 1:
        print("  ?? cannot plant  %-46s (%d matches - the code moved)" % (name, n))
        bad += 1
        continue
    io.open(tmp, "w", encoding="utf-8").write(good.replace(old, new, 1))
    r = subprocess.run(["node", os.path.join(HERE, "test_pinch.js"), "--js", tmp],
                       capture_output=True, text=True)
    caught = r.returncode != 0
    named = [l.strip()[6:].split("   ")[0] for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    how = ("by: " + "; ".join(named[:2])) if named else \
          ("the suite could not even run, which is red enough" if caught else "")
    print("  %-7s %-46s %s" % ("caught" if caught else "MISSED", name, how))
    if not caught:
        bad += 1
os.remove(tmp)

r = subprocess.run(["node", os.path.join(HERE, "test_pinch.js"), TARGET],
                   capture_output=True, text=True)
print("\n  unbroken code: %s" % ("green" if r.returncode == 0 else "RED"))
print("  %s\n" % ("every break was caught" if not bad else
                  "%d break(s) went unnoticed - the tests are not good enough" % bad))
sys.exit(1 if bad or r.returncode else 0)
