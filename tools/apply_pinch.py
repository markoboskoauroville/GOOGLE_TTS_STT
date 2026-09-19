#!/usr/bin/env python3
"""Add pinch-to-resize to the reader page, in every copy of it at once.

THE RECORD OF HOW THE CHANGE WAS MADE, kept so it can be re-made or read.

The reader page lives three times and always will: as src/45_reader.html here,
and inside each of MA Reader's two installers as a heredoc. Editing it three
times by hand is the failure the manifest names by name - two copies with a
rule about keeping them in step are still two copies, and the rule is
eventually not followed. So it was edited once, from here, and each file was
checked afterwards to be byte-identical to what this produces.

    python3 tools/apply_pinch.py FILE...            patch
    python3 tools/apply_pinch.py --check FILE...    exit 1 if one is not patched

    FILE is src/45_reader.html, or either of
    MA_READER_TERMUX_MACOS/3sh_i_ma_reader_v3_{termux,macos}.sh

Already-patched files are left alone, so it is safe to run twice. The server
edits at the end are applied only to the two installers, which are the only
copies that have a server.py inside them.
"""
import io, sys

# ---------------------------------------------------------------- 1. CSS

CSS_OLD = """.reader-scroll{flex:1; overflow-y:auto; padding:18px 16px 24px;
  background:var(--page); -webkit-overflow-scrolling:touch;
  transition:background .25s}"""

CSS_NEW = """.reader-scroll{flex:1; overflow-y:auto; padding:18px 16px 24px;
  background:var(--page); -webkit-overflow-scrolling:touch;
  transition:background .25s;
  /* ONE FINGER PANS, TWO FINGERS ARE OURS.
     This one word is what makes the pinch possible at all. Without it the
     browser owns any two-finger gesture and magnifies the whole page, and
     asking it to stop later - with preventDefault on the first touchmove -
     is too late: by then Chrome has committed to a scroll and the events
     arrive with cancelable already false. touch-action is the only way to
     say so BEFORE the first finger lands. pan-y, not none, because the
     ordinary one-finger scroll must keep its native feel. */
  touch-action:pan-y}"""

# A code block scrolls sideways, and pan-y on its ancestor would have taken
# that away. Naming both axes here gives it back without giving back the zoom.
PRE_OLD = """  overflow-x:auto; -webkit-overflow-scrolling:touch}
.doc.md pre code{"""
PRE_NEW = """  overflow-x:auto; -webkit-overflow-scrolling:touch;
  touch-action:pan-x pan-y}
.doc.md pre code{"""

PILL = """
/* The number two fingers are changing, while they change it. It sits at the
   top, clear of the hand, ignores touches, and leaves on its own. */
.pinch-pill{position:fixed; left:50%; z-index:96; pointer-events:none;
  top:calc(env(safe-area-inset-top, 0px) + 14px);
  transform:translateX(-50%) scale(.96);
  background:var(--panel); border:1px solid var(--line); color:var(--text);
  border-radius:999px; padding:7px 16px; font-size:13px; font-weight:600;
  letter-spacing:.04em; box-shadow:0 4px 18px rgba(0,0,0,.45);
  opacity:0; transition:opacity .16s, transform .16s}
.pinch-pill.on{opacity:1; transform:translateX(-50%) scale(1)}
"""

# ---------------------------------------------------------------- 2. applySize

SIZE_OLD = """function applySize(){
  const fs = 13 + ST.size*2;                 // 15..41 px
  const col = 400 + ST.size*46;
  document.documentElement.style.setProperty("--read", fs+"px");
  document.documentElement.style.setProperty("--col", col+"px");
  const sv=$("#sizeVal"); if(sv) sv.textContent = fs;
  const sv2=$("#sizeVal2"); if(sv2) sv2.textContent = fs;
}"""

SIZE_NEW = '''/* A size that is not a number used to arrive exactly as it was found. The
   reader's state file is written by the browser and read back with no
   arithmetic in between, so a corrupted file, an older build, or somebody
   with the console open could put a string in it - and a string made
   --read into "NaNpx", which a browser discards WITHOUT SAYING SO. The text
   then sat at the 21px in the stylesheet, the readout said NaN, and the
   letter size could not be moved by the stepper or by a pinch, because every
   sum starting at NaN ends at NaN. Nothing anywhere reported a fault.

   So every route into ST.size goes past here first. parseFloat, because a
   number that arrived as text is still a number; the NaN test written as
   n === n, because that is the one comparison NaN fails; and the same two
   limits the stepper uses, so the file can never hold a size the buttons
   could not have produced. */
function sizeOf(v, dflt){
  const n = parseFloat(v);
  return (n === n) ? Math.max(SIZE_MIN, Math.min(SIZE_MAX, n)) : dflt;
}

/* ST.size was a whole step for as long as a stepper was the only thing that
   moved it. A pinch moves it continuously, so it is a real number now and
   every consumer has to survive 7.3 as well as 7. The pixels are rounded to
   a tenth: fine enough that growth looks smooth, coarse enough that two
   frames a hair apart do not each pay for a reflow. The readouts still print
   whole pixels, because nobody wants to read 23.4. */
function applySize(){
  const fs = Math.round((13 + ST.size*2)*10)/10;   // 15..41 px
  const col = Math.round(400 + ST.size*46);
  document.documentElement.style.setProperty("--read", fs+"px");
  document.documentElement.style.setProperty("--col", col+"px");
  const sv=$("#sizeVal"); if(sv) sv.textContent = Math.round(fs);
  const sv2=$("#sizeVal2"); if(sv2) sv2.textContent = Math.round(fs);
}

/* ---------- PINCH: TWO FINGERS CHANGE THE LETTER SIZE ----------

   This is NOT the browser's zoom, and the difference is the whole point.
   Zoom magnifies the page as a picture: the line breaks stay where they
   were, the column keeps its old width in old pixels, and the right-hand
   edge of every line goes off the screen, so reading turns into dragging
   sideways once per line. What two fingers do here is the A- / A+ stepper
   from Settings, run continuously - the type grows and the text REFLOWS into
   the same column, so nothing ever leaves the screen.

   Three things had to be true before it felt like a gesture rather than a
   trick.

   THE BROWSER MUST BE TOLD FIRST. See touch-action on .reader-scroll above.

   THE TEXT MUST STAY UNDER THE FINGERS. Growing type from the top of the
   document pushes the line you were reading downward and off the bottom, and
   the gesture becomes a hunt for your place. So the line under the middle of
   the pinch is remembered before anything moves, and after every resize the
   scroll is corrected so that line has not shifted a pixel. You resize
   around the sentence you are looking at, which is the only one you care
   about.

   IT MUST NOT COST A SENTENCE. A tap in the reading area skips forward one
   sentence, and letting go of a pinch can arrive as a click. Any click
   within 400 ms of the end of a pinch is swallowed at the document, in the
   capture phase, so it never reaches the tap handler at all - stopping it at
   the scroller would be too late, because that handler is on the scroller.

   Resizing does not touch the audio. The clip that is playing goes on
   playing, and the highlight lands on the same words in their new places,
   because the highlight has always been spans in the text rather than
   coordinates on the screen. */
const PINCH = { live:false, d0:1, size0:4, sc:null, anchor:null, anchorY:0,
                pending:0, raf:0, guard:0, hideT:null };

function pinchDist(t){
  const dx = t[0].clientX - t[1].clientX, dy = t[0].clientY - t[1].clientY;
  return Math.sqrt(dx*dx + dy*dy) || 1;     /* never zero: it is a divisor */
}

/* What is under the middle of the pinch, and how far down the window it sits.
   elementFromPoint can hand back a word span, a paragraph, the .doc itself,
   or nothing at all when the middle falls in the margin. Any of those is a
   good enough anchor as long as it belongs to this scroller; when it is
   none of them, the first child of the scroller is a stand-in that at least
   keeps the top of the text still. */
function pinchAnchor(sc, x, y){
  let el = document.elementFromPoint(x, y);
  if(!el || !sc.contains(el)) el = sc.firstElementChild;
  PINCH.anchor  = el || null;
  PINCH.anchorY = el ? el.getBoundingClientRect().top : 0;
}

/* Put the anchor back where it was. An element that has been re-rendered
   under us is no longer in the document and reports a rectangle of zeroes,
   which would throw the scroll to the top of the text - so notice that and
   stop anchoring, rather than anchor to nothing. */
function pinchKeepPlace(){
  const el = PINCH.anchor, sc = PINCH.sc;
  if(!el || !sc) return;
  if(el.isConnected === false){ PINCH.anchor = null; return; }
  sc.scrollTop += el.getBoundingClientRect().top - PINCH.anchorY;
}

function pinchPill(){
  let p = document.getElementById("pinchPill");
  if(!p){
    p = document.createElement("div");
    p.id = "pinchPill"; p.className = "pinch-pill";
    document.body.appendChild(p);
  }
  return p;
}
function pinchShow(){
  const p = pinchPill();
  p.textContent = Math.round(13 + ST.size*2) + " px";
  p.classList.add("on");
  clearTimeout(PINCH.hideT); PINCH.hideT = null;
}
function pinchFade(){
  const p = document.getElementById("pinchPill"); if(!p) return;
  clearTimeout(PINCH.hideT);
  PINCH.hideT = setTimeout(()=>{ p.classList.remove("on"); }, 700);
}

function pinchApply(size){
  if(!(size === size)) return;              /* NaN, from a degenerate pinch */
  ST.size = Math.max(SIZE_MIN, Math.min(SIZE_MAX, size));
  applySize();
  pinchKeepPlace();
  pinchShow();
}

/* A long text reflows on every size change, and fingers deliver touchmove far
   faster than a page can lay out. Only the newest size is worth anything, so
   hold it and spend one layout per frame. */
function pinchQueue(size){
  PINCH.pending = size;
  if(PINCH.raf) return;
  PINCH.raf = requestAnimationFrame(()=>{
    PINCH.raf = 0; pinchApply(PINCH.pending);
  });
}

function wirePinch(){
  document.addEventListener("touchstart", (e)=>{
    if(e.touches.length !== 2) return;
    const t = e.target;
    const sc = (t && t.closest) ? t.closest(".reader-scroll") : null;
    if(!sc) return;
    /* Editing the Markdown source is typing, and two fingers in a text field
       belong to the field and its own selection handles. */
    if(document.body.classList.contains("mode-edit")) return;
    PINCH.live  = true;
    PINCH.sc    = sc;
    PINCH.d0    = pinchDist(e.touches);
    PINCH.size0 = ST.size;
    pinchAnchor(sc, (e.touches[0].clientX + e.touches[1].clientX)/2,
                    (e.touches[0].clientY + e.touches[1].clientY)/2);
  }, true);

  document.addEventListener("touchmove", (e)=>{
    if(!PINCH.live || e.touches.length !== 2) return;
    if(e.cancelable) e.preventDefault();
    /* The ratio is measured against where the fingers STARTED, not against
       the last frame. Frame to frame, the rounding of each step would
       compound, and a slow pinch would end up somewhere different from a
       fast one across the same distance. */
    const fs0 = 13 + PINCH.size0*2;
    pinchQueue(((fs0 * (pinchDist(e.touches) / PINCH.d0)) - 13) / 2);
  }, {passive:false, capture:true});

  const done = ()=>{
    if(!PINCH.live) return;
    PINCH.live = false;
    /* A queued frame that never ran would lose the last of the gesture, so
       spend it now rather than cancelling it. */
    if(PINCH.raf){
      cancelAnimationFrame(PINCH.raf); PINCH.raf = 0;
      pinchApply(PINCH.pending);
    }
    PINCH.anchor = null; PINCH.sc = null;
    PINCH.guard  = Date.now() + 400;
    pinchFade();
    persist();
  };
  /* Either finger leaving ends it. The one still down goes back to scrolling,
     which is what it would have been doing on its own. */
  document.addEventListener("touchend", done, true);
  document.addEventListener("touchcancel", done, true);

  /* The same gesture on a trackpad. A Mac reports a pinch as a wheel event
     with ctrl held down - it is not held down, the system says so on the
     pinch's behalf - and a desktop browser reads a real ctrl+wheel as zoom.
     Both mean "resize this", and neither should scroll or zoom the page.
     exp() rather than a fixed step, so the same roll of the fingers moves
     the same proportion at 15 px as at 40. */
  document.addEventListener("wheel", (e)=>{
    if(!e.ctrlKey) return;
    const t = e.target;
    const sc = (t && t.closest) ? t.closest(".reader-scroll") : null;
    if(!sc) return;
    if(e.cancelable) e.preventDefault();
    PINCH.sc = sc;
    pinchAnchor(sc, e.clientX, e.clientY);
    pinchApply((((13 + ST.size*2) * Math.exp(-e.deltaY/220)) - 13) / 2);
    PINCH.anchor = null; PINCH.sc = null;
    pinchFade();
    persist();                 /* debounced 250 ms: a roll writes once */
  }, {passive:false});

  /* The swallowed click. Capture at the document runs before capture at the
     scroller, so stopping it here means the tap handler never sees it. */
  document.addEventListener("click", (e)=>{
    if(Date.now() < PINCH.guard){ e.stopPropagation(); e.preventDefault(); }
  }, true);
}'''

# ---------------------------------------------------------------- 3. stepper

STEP_OLD = """    ST.size = Math.max(SIZE_MIN, Math.min(SIZE_MAX, ST.size + d)); applySize();"""
STEP_NEW = """    /* A pinch can leave the size between two steps. A+ and A- put it back
       on one: round first, then move, or the buttons would carry the
       fraction forever and never land on the number they print. */
    ST.size = Math.max(SIZE_MIN, Math.min(SIZE_MAX, Math.round(ST.size) + d));
    applySize();"""

# ---------------------------------------------------------------- 4. wiring

WIRE_OLD = """  wireCenterTaps("#offReaderScroll", true);"""
WIRE_NEW = """  wireCenterTaps("#offReaderScroll", true);
  /* One handler for both reading views and for the trackpad. It finds its own
     scroller from the target, so a third reading surface would be covered by
     the day it exists, without a line here. */
  wirePinch();"""

# ------------------------------------------- 5. the server, MA Reader only

# int() would quietly truncate every pinch back to a whole step on the next
# load: the gesture would look like it worked and be gone after a restart.
# This is exactly the silent failure the manifest says to write down.
SRV_OLD = """    _num("size", 1, 14, 2, 0)"""
SRV_NEW = """    # two decimals, not zero: a pinch leaves the size between two steps,
    # and rounding it here would undo the gesture on the next page load
    # while looking, from the browser, as though it had worked.
    _num("size", 1, 14, 2, 2)"""
SRV2_OLD = """    st["volume"] = int(st["volume"]); st["size"] = int(st["size"])"""
SRV2_NEW = """    st["volume"] = int(st["volume"])"""


# the one line where a state file becomes ST.size
REST_OLD = ("    ST.size = st.size||13; ST.autoplay = (st.autoplay!==false); "
            "ST.focus = !!st.focus;")
REST_NEW = ("    ST.size = sizeOf(st.size, 13); ST.autoplay = (st.autoplay!==false); "
            "ST.focus = !!st.focus;")

EDITS = [(CSS_OLD, CSS_NEW), (PRE_OLD, PRE_NEW), (SIZE_OLD, SIZE_NEW),
         (STEP_OLD, STEP_NEW), (WIRE_OLD, WIRE_NEW), (REST_OLD, REST_NEW)]
SERVER_EDITS = [(SRV_OLD, SRV_NEW), (SRV2_OLD, SRV2_NEW)]
PILL_AFTER = ".pinch-pill.on"


def patch(path, check):
    s = io.open(path, encoding="utf-8").read()
    if "wirePinch" in s:
        if check:
            print("  ok      ", path); return 0
        print("  already  ", path); return 0
    if check:
        print("  STALE    ", path); return 1

    edits = list(EDITS)
    if SRV_OLD in s:                       # the two installers, not the html
        edits += SERVER_EDITS
    for old, new in edits:
        n = s.count(old)
        if n != 1:
            sys.exit("%s: expected 1 of %r, found %d" % (path, old[:48], n))
        s = s.replace(old, new)
    # the pill's CSS goes on the end of the reader's own block
    s = s.replace(PRE_NEW, PRE_NEW, 1)
    s = s.replace(CSS_NEW, CSS_NEW + "\n" + PILL, 1)
    io.open(path, "w", encoding="utf-8").write(s)
    print("  patched  ", path)
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    check = "--check" in args
    files = [a for a in args if not a.startswith("--")]
    bad = 0
    for f in files:
        bad |= patch(f, check)
    sys.exit(bad)
