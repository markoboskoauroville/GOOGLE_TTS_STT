/* TEST 2, the part a browser would only report by going blank.
   A syntax error anywhere in a 6000-line inline script does not break the
   pinch - it breaks the whole app, silently, with a console message nobody on
   a phone can see. So the page as SERVED is parsed, every script block of it,
   before anything else is believed. */
const fs = require("fs"), path = require("path"), cp = require("child_process");
const ROOT = path.dirname(__dirname);
const FROM = process.argv[2] || path.join(ROOT, "src", "45_reader.html");
/* the page as it SHIPS - out of the installer's heredoc when that is what it
   is given, so this is the same check for all three copies */
const html = cp.execFileSync("python3",
  [path.join(__dirname, "pinch_extract.py"), FROM, "--page"],
  {encoding:"utf8", maxBuffer: 64*1024*1024});
console.log("  under test: " + path.basename(FROM));
let fails = 0, n = 0;

const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let m;
while((m = re.exec(html))){
  n++;
  const body = m[1];
  const line = html.slice(0, m.index).split("\n").length;
  try{
    new Function(body);
    console.log("  pass  script block %d (from line %d, %d lines) parses",
                n, line, body.split("\n").length);
  }catch(e){
    fails++;
    console.log("  FAIL  script block %d (from line %d): %s", n, line, e.message);
  }
}
console.log("  %d inline script block(s)", n);
if(!n){ console.log("  FAIL  no inline script found - the test is looking in the wrong place"); fails++; }

/* the CSS: one unbalanced brace silently kills every rule after it */
const sre = /<style[^>]*>([\s\S]*?)<\/style>/gi;
let s, blocks = 0;
while((s = sre.exec(html))){
  blocks++;
  const css = s[1].replace(/\/\*[\s\S]*?\*\//g, "");   // comments hold braces
  const open = (css.match(/{/g)||[]).length, close = (css.match(/}/g)||[]).length;
  if(open === close) console.log("  pass  style block %d balanced (%d rules)", blocks, open);
  else { fails++; console.log("  FAIL  style block %d: %d { against %d }", blocks, open, close); }
}

/* and the thing itself is actually in what was served */
const must = [
  ["the scroller claims two-finger gestures", /\.reader-scroll\{[^}]*touch-action:pan-y\}/],
  ["code blocks keep their sideways scroll", /touch-action:pan-x pan-y/],
  ["the gesture is wired up at boot",        /\n  wirePinch\(\);/],
  ["the stepper rounds off a pinch",         /Math\.round\(ST\.size\) \+ d/],
  ["applySize survives a fraction",          /Math\.round\(\(13 \+ ST\.size\*2\)\*10\)\/10/],
];
for(const [name, rx] of must){
  if(rx.test(html)) console.log("  pass  " + name);
  else { fails++; console.log("  FAIL  " + name); }
}
console.log("\n  " + (fails ? fails + " FAILED" : "page is sound") + "\n");
process.exit(fails ? 1 : 0);
