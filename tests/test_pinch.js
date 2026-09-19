/* TEST 1 + TEST 2 for pinch-to-resize.
   The code under test is lifted verbatim out of the patched page, so this
   tests what ships, not a retyped copy of it. The DOM is a stub small enough
   to reason about: a scroller with a known scrollTop, one anchor element
   whose rectangle moves with the font size the way a real line would. */
const fs_ = require("fs"), path = require("path"), cp = require("child_process");

/* WHAT IS UNDER TEST is whatever is shipping, lifted out of it by
   pinch_extract.py - never a copy kept beside these tests, which would only
   ever prove that the copy agrees with itself.

     node tests/test_pinch.js                      src/45_reader.html
     node tests/test_pinch.js <file>               that page, or that installer
     node tests/test_pinch.js --js <file>          an already-extracted mutant,
                                                     which is how the mutation
                                                     run plants its breaks */
const ROOT = path.dirname(__dirname);
const argv = process.argv.slice(2);
let SRC, FROM;
if(argv[0] === "--js"){
  FROM = argv[1];
  SRC  = fs_.readFileSync(FROM, "utf8");
} else {
  FROM = argv[0] || path.join(ROOT, "src", "45_reader.html");
  SRC  = cp.execFileSync("python3",
           [path.join(__dirname, "pinch_extract.py"), FROM, "--js"],
           {encoding:"utf8", maxBuffer: 64*1024*1024});
}
console.log("  under test: " + path.basename(FROM) + "   (" +
            SRC.split("\n").length + " lines, lifted from the shipped file)");

let fails = 0, ran = 0;
function ok(name, cond, extra){
  ran++;
  if(!cond){ fails++; console.log("  FAIL  " + name + (extra?"   "+extra:"")); }
  else console.log("  pass  " + name + (extra?"   "+extra:""));
}
function near(a,b,eps){ return Math.abs(a-b) <= (eps===undefined?0.051:eps); }

/* ---------------- the stub world ---------------- */
function makeWorld(){
  const W = {};
  W.SIZE_MIN = 1; W.SIZE_MAX = 14;
  W.ST = { size: 4 };
  W.cssVars = {};
  W.persists = 0;
  W.rafQ = [];
  W.now = 1000000;
  W.listeners = {};
  W.timers = [];

  /* One line of text. Its distance from the top of the SCROLLER grows in
     proportion to the font size - which is what a real reflow does to
     everything above it - and its screen position is that minus scrollTop. */
  W.LINE_AT_15PX = 900;              // px from the top of the document
  W.scroller = {
    scrollTop: 400,
    contains: ()=>true,
    firstElementChild: null,
    getBoundingClientRect: ()=>({top:0}),
    closest: (s)=> s===".reader-scroll" ? W.scroller : null,
    addEventListener: ()=>{}
  };
  W.line = {
    isConnected: true,
    getBoundingClientRect(){
      if(!this.isConnected) return {top:0};      // what a detached node reports
      const fs = parseFloat(W.cssVars["--read"]) || 15;
      const docTop = W.LINE_AT_15PX * (fs/15);
      return { top: docTop - W.scroller.scrollTop };
    }
  };
  W.scroller.firstElementChild = W.line;

  const el = (id)=> ({id, textContent:"", classList:{
      add(){this.on=true;}, remove(){this.on=false;}, on:false},
      appendChild(){}, });
  W.pill = null;
  W.document = {
    body:{ classList:{ contains:()=>false }, appendChild:(n)=>{ W.pill=n; } },
    getElementById:(id)=> id==="pinchPill" ? W.pill : null,
    createElement:()=> ({id:"", className:"", textContent:"",
        classList:{ add(){this._on=true;}, remove(){this._on=false;}, _on:false }}),
    elementFromPoint:()=> W.line,
    documentElement:{ style:{ setProperty:(k,v)=>{ W.cssVars[k]=v; } } },
    addEventListener:(t,f,o)=>{ (W.listeners[t]=W.listeners[t]||[]).push(f); }
  };
  W.$ = (sel)=> null;
  W.persist = ()=>{ W.persists++; };
  W.requestAnimationFrame = (f)=>{ W.rafQ.push(f); return W.rafQ.length; };
  W.cancelAnimationFrame = (h)=>{ W.rafQ[h-1] = null; };
  W.setTimeout = (f,ms)=>{ W.timers.push(f); return W.timers.length; };
  W.clearTimeout = (h)=>{ if(h) W.timers[h-1]=null; };
  W.Date = { now: ()=> W.now };
  W.flush = ()=>{ const q=W.rafQ; W.rafQ=[]; q.forEach(f=> f && f()); };

  const fn = new Function("SIZE_MIN","SIZE_MAX","ST","$","persist","document",
      "requestAnimationFrame","cancelAnimationFrame","setTimeout",
      "clearTimeout","Date","Math","parseFloat",
      SRC + "\nreturn {applySize, sizeOf, PINCH, pinchDist, pinchAnchor," +
      " pinchKeepPlace, pinchApply, pinchQueue, wirePinch};");
  W.api = fn(W.SIZE_MIN, W.SIZE_MAX, W.ST, W.$, W.persist, W.document,
      W.requestAnimationFrame, W.cancelAnimationFrame, W.setTimeout,
      W.clearTimeout, W.Date, Math, parseFloat);
  W.api.wirePinch();
  W.fire = (type, ev)=> (W.listeners[type]||[]).forEach(f=>f(ev));
  return W;
}
function touches(x1,y1,x2,y2){
  const t=[{clientX:x1,clientY:y1},{clientX:x2,clientY:y2}];
  t.length=2; return t;
}
function tev(t, cancelable){
  let prevented=false;
  return { touches:t, target:null, cancelable:cancelable!==false,
           preventDefault(){prevented=true;}, get prevented(){return prevented;} };
}
function px(W){ return parseFloat(W.cssVars["--read"]); }

console.log("\n=== TEST 1  the mechanism alone ===");

/* the size <-> pixel rule, at both ends and past them */
{
  const W = makeWorld();
  W.ST.size = 1;  W.api.applySize(); ok("SIZE_MIN is 15 px", px(W)===15, px(W)+"px");
  W.ST.size = 14; W.api.applySize(); ok("SIZE_MAX is 41 px", px(W)===41, px(W)+"px");
  W.ST.size = 4;  W.api.applySize(); ok("the default is 21 px", px(W)===21, px(W)+"px");
  W.ST.size = 7.35; W.api.applySize();
  ok("a fraction survives applySize", near(px(W), 27.7), px(W)+"px");
  ok("the column is a whole number", /^\d+px$/.test(W.cssVars["--col"]),
     W.cssVars["--col"]);
}

/* the clamp: a pinch cannot push the size out of the range the stepper uses */
{
  const W = makeWorld();
  W.api.pinchApply(99);  ok("a huge pinch clamps to SIZE_MAX", W.ST.size===14, "size="+W.ST.size);
  W.api.pinchApply(-99); ok("a tiny pinch clamps to SIZE_MIN", W.ST.size===1,  "size="+W.ST.size);
  const before = W.ST.size;
  W.api.pinchApply(NaN);
  ok("NaN is refused, not stored", W.ST.size===before, "size="+W.ST.size);
}

/* what a state file is allowed to become. The default asked for is 13, which
   is the number the app has always fallen back to when the key was absent. */
{
  const W = makeWorld(), sz = W.api.sizeOf;
  ok("a whole number passes through", sz(7,13)===7);
  ok("a pinched fraction passes through", sz(7.35,13)===7.35);
  ok("a number that arrived as text is still a number", sz("8.5",13)===8.5);
  ok("a word is not a size", sz("banana",13)===13);
  ok("null is not a size", sz(null,13)===13);
  ok("undefined is not a size - the key was never written", sz(undefined,13)===13);
  ok("true is not a size", sz(true,13)===13);
  ok("an object is not a size", sz({},13)===13);
  ok("an empty string is not a size", sz("",13)===13);
  ok("NaN itself is not a size", sz(NaN,13)===13);
  ok("above the ceiling comes back as the ceiling", sz(900,13)===14);
  ok("below the floor comes back as the floor", sz(-4,13)===1);
  ok("zero is out of range and clamps rather than jumping to the default",
     sz(0,13)===1, sz(0,13));
  ok("Infinity does not pass for a size", sz(Infinity,13)===14);
  /* the failure this exists to stop: a bad size used to reach applySize */
  W.ST.size = sz("banana",13); W.api.applySize();
  ok("a corrupted state file cannot make --read into NaNpx",
     !/NaN/.test(W.cssVars["--read"]), W.cssVars["--read"]);
  ok("and the pinch can still move the text afterwards",
     (()=>{ const b = px(W);
            W.fire("touchstart",{touches:touches(100,300,200,300),target:W.scroller});
            W.fire("touchmove", tev(touches(80,300,220,300))); W.flush();
            W.fire("touchend",{});
            return px(W) > b; })());
}

/* the distance, including the case that would divide by zero */
{
  const W = makeWorld();
  ok("3-4-5 triangle", W.api.pinchDist(touches(0,0,3,4))===5);
  ok("two fingers on one point is 1, not 0",
     W.api.pinchDist(touches(7,7,7,7))===1);
}

/* the ratio is measured from the START of the gesture, so a slow pinch and a
   fast one over the same distance land on the same size */
{
  const slow = makeWorld(), fast = makeWorld();
  for(const W of [slow,fast]){ W.ST.size=1; W.api.applySize(); }   // 15 px
  slow.fire("touchstart", {touches:touches(0,0,200,0), target:slow.scroller});
  fast.fire("touchstart", {touches:touches(0,0,200,0), target:fast.scroller});
  for(let d=205; d<=260; d+=5){                       // twelve small moves
    slow.fire("touchmove", tev(touches(0,0,d,0))); slow.flush();
  }
  fast.fire("touchmove", tev(touches(0,0,260,0))); fast.flush();   // one big
  ok("slow and fast pinches agree", near(slow.ST.size, fast.ST.size, 1e-9),
     slow.ST.size.toFixed(4)+" vs "+fast.ST.size.toFixed(4));
  ok("the type grows by the same ratio as the fingers",
     near(px(fast), 15*1.3, 0.051), px(fast)+"px, wanted "+(15*1.3));
  ok("neither one is sitting at the ceiling, or they would agree for the "+
     "wrong reason", slow.ST.size < 14 && fast.ST.size < 14);
}

/* the anchor arithmetic: the remembered line does not move on the screen */
{
  const W = makeWorld();
  W.ST.size = 4; W.api.applySize();                 // 21px
  W.scroller.scrollTop = 400;
  const screenYBefore = W.line.getBoundingClientRect().top;
  W.api.PINCH.sc = W.scroller;
  W.api.pinchAnchor(W.scroller, 200, screenYBefore);
  W.ST.size = 10; W.api.applySize();                // 33px, everything moves
  W.api.pinchKeepPlace();
  const screenYAfter = W.line.getBoundingClientRect().top;
  ok("the anchored line stays on the same screen row",
     near(screenYBefore, screenYAfter, 0.5),
     screenYBefore.toFixed(1)+" -> "+screenYAfter.toFixed(1));
}

console.log("\n=== TEST 2  wired up, driven the way a finger does ===");
{
  const W = makeWorld();
  W.ST.size = 4; W.api.applySize();
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  ok("the gesture is claimed", W.api.PINCH.live===true);
  const ev = tev(touches(90,300,210,300));
  W.fire("touchmove", ev); W.flush();
  ok("the browser's own zoom is refused", ev.prevented===true);
  ok("spreading makes the type bigger", px(W) > 21, px(W)+"px");
  ok("one layout per frame, not one per move",
     (()=>{ const before = px(W);
            W.fire("touchmove", tev(touches(80,300,220,300)));
            W.fire("touchmove", tev(touches(70,300,230,300)));
            const mid = px(W); W.flush();
            return mid===before && px(W)>before; })());
  W.fire("touchend", {});
  ok("the gesture ends", W.api.PINCH.live===false);
  ok("it is written down once", W.persists===1, "persist calls="+W.persists);
  ok("the pill shows the whole-pixel number",
     W.pill && W.pill.textContent === Math.round(px(W))+" px", W.pill&&W.pill.textContent);
}
{
  /* the same, watching the page rather than the number: the line under the
     fingers must not move while the type grows around it */
  const W = makeWorld();
  W.ST.size = 4; W.api.applySize();
  W.scroller.scrollTop = 400;
  const screenY = W.line.getBoundingClientRect().top;
  W.document.elementFromPoint = ()=> W.line;
  W.fire("touchstart", {touches:touches(100,screenY,200,screenY),
                        target:W.scroller});
  W.fire("touchmove", tev(touches(60,screenY,240,screenY))); W.flush();
  ok("the line under the fingers has not moved",
     near(W.line.getBoundingClientRect().top, screenY, 0.5),
     screenY.toFixed(1)+" -> "+W.line.getBoundingClientRect().top.toFixed(1));
  ok("and the page did scroll to keep it there, rather than doing nothing",
     W.scroller.scrollTop !== 400, "scrollTop 400 -> "+W.scroller.scrollTop.toFixed(0));
  W.fire("touchend", {});
}
{
  /* the last frame of a gesture: let go before it has been drawn */
  const W = makeWorld();
  W.ST.size = 4; W.api.applySize();
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  W.fire("touchmove", tev(touches(80,300,220,300)));      // NOT flushed
  const undrawn = px(W);
  W.fire("touchend", {});
  ok("the frame still in the queue when the fingers left is spent, not dropped",
     px(W) !== undrawn && near(px(W), 21*1.4, 0.06),
     undrawn+"px -> "+px(W)+"px");
}
/* pinching in */
{
  const W = makeWorld();
  W.ST.size = 8; W.api.applySize();
  const before = px(W);
  W.fire("touchstart", {touches:touches(50,300,250,300), target:W.scroller});
  W.fire("touchmove", tev(touches(120,300,180,300))); W.flush();
  ok("pinching in makes the type smaller", px(W) < before, before+" -> "+px(W));
}
/* the swallowed click */
{
  const W = makeWorld();
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  W.fire("touchmove", tev(touches(90,300,210,300))); W.flush();
  W.fire("touchend", {});
  let stopped=false;
  W.fire("click", {stopPropagation:()=>{stopped=true;}, preventDefault:()=>{}});
  ok("the click that ends a pinch does not skip a sentence", stopped===true);
  W.now += 500;                                  // 400 ms guard has expired
  stopped=false;
  W.fire("click", {stopPropagation:()=>{stopped=true;}, preventDefault:()=>{}});
  ok("an ordinary tap half a second later still counts", stopped===false);
}
/* the trackpad */
{
  const W = makeWorld();
  W.ST.size = 4; W.api.applySize();
  let prevented=false;
  W.fire("wheel", {ctrlKey:true, deltaY:-100, clientX:200, clientY:300,
      cancelable:true, target:W.scroller, preventDefault:()=>{prevented=true;}});
  ok("ctrl+wheel enlarges", px(W) > 21, px(W)+"px");
  ok("and does not let the browser zoom", prevented===true);
  const after = px(W);
  W.fire("wheel", {ctrlKey:false, deltaY:-100, clientX:200, clientY:300,
      cancelable:true, target:W.scroller, preventDefault:()=>{}});
  ok("a plain wheel is left alone to scroll", px(W)===after);
}

console.log("\n=== TEST 3  the ugly cases ===");
{
  const W = makeWorld();
  /* a third finger */
  W.ST.size = 4; W.api.applySize();
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  const before = px(W);
  /* the first two fingers MOVE as well, so a version that simply read
     touches[0] and touches[1] and ignored the count would resize here */
  const three = touches(60,300,240,300); three.push({clientX:150,clientY:400});
  W.fire("touchmove", tev(three)); W.flush();
  ok("a third finger is ignored rather than guessed at", px(W)===before);
  W.fire("touchend", {});
}
{
  const W = makeWorld();
  /* touchmove with no touchstart: an event from a gesture begun elsewhere */
  W.ST.size = 4; W.api.applySize();
  const before = px(W);
  W.fire("touchmove", tev(touches(0,0,100,0))); W.flush();
  ok("a move with no start does nothing", px(W)===before);
  W.fire("touchend", {});
  ok("an end with no start writes nothing", W.persists===0);
}
{
  const W = makeWorld();
  /* the anchor is re-rendered out from under us mid-gesture */
  W.ST.size=4; W.api.applySize();
  W.scroller.scrollTop = 400;
  W.api.PINCH.sc = W.scroller;
  W.api.pinchAnchor(W.scroller, 200, 100);
  W.line.isConnected = false;
  W.api.pinchKeepPlace();
  ok("a vanished anchor does not throw the scroll to the top",
     W.scroller.scrollTop===400, "scrollTop="+W.scroller.scrollTop);
  ok("and it stops anchoring rather than anchoring to nothing",
     W.api.PINCH.anchor===null);
}
{
  const W = makeWorld();
  /* the pinch centre falls in the margin: elementFromPoint gives nothing */
  W.document.elementFromPoint = ()=>null;
  W.api.pinchAnchor(W.scroller, 5, 5);
  ok("no element under the fingers falls back to the top of the text",
     W.api.PINCH.anchor === W.line);
  W.document.elementFromPoint = ()=> ({});     // something outside the scroller
  W.scroller.contains = ()=>false;
  W.api.pinchAnchor(W.scroller, 5, 5);
  ok("an element from another scroller is refused",
     W.api.PINCH.anchor === W.line);
}
{
  const W = makeWorld();
  /* two fingers landing outside any reader - the paste box, Settings */
  W.fire("touchstart", {touches:touches(100,300,200,300),
      target:{ closest:()=>null }});
  ok("two fingers off the page are not ours", W.api.PINCH.live===false);
  const ev = tev(touches(90,300,210,300));
  W.fire("touchmove", ev);
  ok("and the browser keeps its own gesture there", ev.prevented===false);
}
{
  const W = makeWorld();
  /* editing the Markdown source */
  W.document.body.classList.contains = (c)=> c==="mode-edit";
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  ok("two fingers in the editor belong to the editor", W.api.PINCH.live===false);
}
{
  const W = makeWorld();
  /* the event arrives already uncancelable */
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  const ev = tev(touches(90,300,210,300), false);
  W.fire("touchmove", ev); W.flush();
  ok("an uncancelable move still resizes", px(W) > 21, px(W)+"px");
  ok("and does not call preventDefault on it", ev.prevented===false);
}
{
  const W = makeWorld();
  /* the same gesture twice in a row, and a cancel instead of an end */
  W.ST.size=4; W.api.applySize();
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  W.fire("touchmove", tev(touches(90,300,210,300))); W.flush();
  const first = W.ST.size;
  W.fire("touchcancel", {});
  ok("a cancelled pinch keeps what it had", W.ST.size===first);
  ok("and is written down", W.persists===1);
  W.fire("touchend", {});
  ok("a second end writes nothing more", W.persists===1);
  W.fire("touchstart", {touches:touches(100,300,200,300), target:W.scroller});
  W.fire("touchmove", tev(touches(90,300,210,300))); W.flush();
  ok("the second pinch starts from where the first stopped",
     W.ST.size > first, first.toFixed(2)+" -> "+W.ST.size.toFixed(2));
}
{
  const W = makeWorld();
  /* pinching at the ceiling and coming back down */
  W.ST.size = 13; W.api.applySize();
  W.fire("touchstart", {touches:touches(0,0,100,0), target:W.scroller});
  W.fire("touchmove", tev(touches(0,0,400,0))); W.flush();
  ok("held at the ceiling", W.ST.size===14, "size="+W.ST.size);
  W.fire("touchmove", tev(touches(0,0,50,0))); W.flush();
  ok("and comes straight back down from the same gesture", W.ST.size < 14,
     "size="+W.ST.size.toFixed(2));
}

console.log("\n" + (fails ? "  " + fails + " FAILED of " + ran
                          : "  all " + ran + " passed") + "\n");
process.exit(fails ? 1 : 0);
