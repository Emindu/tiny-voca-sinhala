"""Pack eSpeak NG data files into one blob: [u32 header len][JSON [[path, offset, size]...]][bytes]."""
import json, os, struct, sys
src, out = sys.argv[1], sys.argv[2]
keep = sys.argv[3:]  # file paths or directories relative to src
files = []
for k in keep:
    p = os.path.join(src, k)
    if os.path.isdir(p):
        for root, _, names in os.walk(p):
            for n in sorted(names):
                files.append(os.path.relpath(os.path.join(root, n), src))
    else:
        files.append(k)
header, blob = [], bytearray()
for f in sorted(set(files)):
    data = open(os.path.join(src, f), "rb").read()
    header.append([f.replace(os.sep, "/"), len(blob), len(data)])
    blob += data
h = json.dumps(header, separators=(",", ":")).encode()
open(out, "wb").write(struct.pack("<I", len(h)) + h + blob)
print(f"{len(header)} files, {len(blob)/1024:.0f} KB -> {out}")
