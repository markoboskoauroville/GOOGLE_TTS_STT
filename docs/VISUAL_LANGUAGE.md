# Visual Language

**How this app looks, in the terminal and on the page, and why.** Read this
before changing anything on either screen.

## The terminal

The installer opens with the same three-part banner every Mantra installer
opens with: the mark, the name and the version on one line, and two dim lines
saying what it is for.

```
    ____  ____  ____
   / ___||_  _||_  _|   GOOGLE TTS AND STT  v1
  | |  _   ||    ||     speak · listen · keys
  | |_| |  ||    ||     one ring, one ledger, one roof
   \____| |__|  |__|
```

Then one line per step, the label left and the verdict right, in a fixed
column so the verdicts stack:

```
  platform  macos
  > python                            3.12.3
  > flask                             ok
  > waitress                          ok
  > ffmpeg                            ok
  > key ring                          21 accounts
  > app                               ok
  > gtt                               ok
  > gtt-update                        ok
```

`ok` green, a skip grey and named rather than silent, a fault red. The line is
padded on the plain text and the colour wrapped around it afterwards — printf
counts the bytes of an escape sequence as width, so a coloured string handed to
`%-34s` comes out short by exactly the length of its escapes and every verdict
on the right walks left. That is the easiest way to break the column and it is
invisible until the colours are on.

Nothing waits without a deadline and no step is silent. A missing ffmpeg prints
what it costs and how to fix it rather than being discovered later by a failed
transcription.

## The menu

`gtt` draws four quadrants, the same shape MAHA COMMUTE uses, because the hand
should not have to learn a second layout.

```
  GOOGLE TTS AND STT v1
  +---------------------+---------------------+
  |1 Speak              |2 Listen             |
  |  text becomes audio |  audio becomes text |
  |  thirty voices      |  any format ffmpeg  |
  +---------------------+---------------------+
  |3 Keys               |4 free               |
  |  import a key file  |                     |
  |  what is left today |  room for a fourth  |
  +---------------------+---------------------+

  1 run      2 test     3 keys     4 output
  5 update   6 import   0 quit
```

Three lines to a quadrant, always three. The label, what it does, what it is
for. The fourth quadrant is drawn while it is empty, because a screen that
rearranges itself when the state changes is a screen the hand cannot learn.
Twenty-one characters inside each quadrant, forty-five columns overall, which
fits a phone terminal with room to spare. Words are not clipped to fit; where a
sentence is too long a shorter one is written.

## The page

### The rule everything follows from

**Nothing appears. Nothing disappears. Things become active or inactive.**

The player is drawn before there is anything to play. The result box is drawn
before there is a result, saying *nothing spoken yet*. Both are dimmed with
opacity and pointer-events, properties that do not touch layout, so an element
occupies exactly the same space idle as it does active. Speaking does not
rearrange the screen; it fills in what was already there.

The failure this forbids is the natural way to build it: a text box, then a
button that appears once there is text, then a player that replaces both. Three
layouts, two jumps, and the tallest element arriving last so everything below it
slides down.

### One language across the three tabs

Tabs are views of one application. The output box on Speak and the output box on
Listen are the same box, same padding, same dim state, same place. Two
implementations of one thing are two places to drift apart, and the drift always
shows as the same control behaving differently depending on where you found it.

### Colour carries state, and only state

| | |
|---|---|
| amber `#F59E0B` | the lit thing, the accent, the one control that acts |
| sand `#F2DDB4` | ink |
| slate `#23303D` | rules and inactive surfaces |
| near-black `#0B0D10` `#141A21` | ground and panels |
| green | a key that is live |
| red `#EF4444` | a fault, and nothing else |

A key with no credit and a revoked key are red because they are faults. A key at
its daily wall is **not** red: it is a working account that has done its work
for the day, and red on a screen opened forty times a day makes every visit feel
like an incident.

### The budget is one number, then the detail

The Keys tab leads with hours of speech left today, large and alone, because
that is the question. The per-model table is underneath for when the single
number is not enough, and a row whose daily limit has never actually been
reached is marked with a star and explained, rather than being presented as
though it were measured.

### The picker sits above the test button, not behind a dialogue

Adding accounts and testing accounts are the same job five minutes apart, so
they are on the same tab in the order they happen: the file input first, then
what the import did, then the test button, then what the test found. No modal,
no wizard, no second screen. The import result box is drawn before there is an
import, saying *nothing imported this session*, like every other output box in
the app.

What it reports is what was actually done, in three lines: how many keys were in
the file, how many were added, how many were already held. A key that was
skipped is listed with the name it already has in the ring, because the useful
question at that moment is *which one was this* and not *how many*.

### Never the whole key

Six characters at the front, four at the back, an ellipsis between. The page
never receives more than that. Both Gemini formats are matched, `AIza…` and
`AQ.…`, because a filter written for one finds nothing in a file full of the
other and then prints what it failed to hide.
