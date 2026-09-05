# Not tested

The short list, for anyone who does not want to read all of
[`../DELIVERY_RECORD.md`](../DELIVERY_RECORD.md).

- Termux on the phone. Only the Linux and macOS paths were run. In particular
  `pkg install -y python` and `pkg install -y ffmpeg`, which v3 added, have
  never executed: there is no pkg on the machine that built this.
- The live provider, at v3. Test 2 needs a working key ring and the old keys
  are retired.
- macOS on real hardware.
- An upgrade from a genuinely older release. There is not one yet.
- `gtt-update` end to end. It needs a newer version in the repository than the
  one installed. `get.sh` has been run against the live repository.
- A key file that is not UTF-8.
- A key file over 8 MB, which is refused by size rather than read.
- waitress serving. It is installed; the app still starts the Flask dev server.
- The daily limit for `gemini-3.1-flash-lite`, never reached.
- The daily limit for `gemini-3.5-flash`, assumed to match its sibling at 20.
- A request that is in flight when midnight Pacific arrives.
