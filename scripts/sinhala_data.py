"""Download Sinhala speech corpora and turn them into tiny-voca Parquet shards.

    python scripts/sinhala_data.py download --source pathnirvana --dest raw
    python scripts/sinhala_data.py build --pathnirvana raw/pathnirvana --output data

``download`` sources:

* ``pathnirvana``: Path Nirvana Sinhala TTS dataset v2 (github.com/pnfo/sinhala-tts-dataset),
  about 13.8 hours: Ven. Mettananda (male, ~11.8 h) and Mrs. Oshadi (female, ~2 h).
  Fetched from the repository's latest GitHub release. Licence: GPL-3.0, and the
  speakers allow only non-obscene, non-offensive speech generation.
* ``pathnirvana-old``: the first release (Mrs. Oshadi, ~7 h), stored in the git
  repository itself. Used automatically if the release cannot be fetched.
* ``openslr30``: Google's Sinhala TTS corpus (openslr.org/30), multi-speaker,
  48 kHz. Licence: CC BY-SA 4.0. Optional extra voices.

``build`` resamples to 24 kHz mono, trims edge silence, drops clips outside
1-15 s, removes the unspoken ``-පෙ-`` marker, splits train/validation/test BY
SENTENCE (the same sentence never lands in two splits, across all voices), and
writes ``<output>/{train,validation,test}-NNNNN.parquet`` plus
``<output>/config.json`` with the voice names for ``--config``.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import unicodedata
import urllib.request
import zipfile

PATHNIRVANA_REPO = "pnfo/sinhala-tts-dataset"
OPENSLR_MIRRORS = ("https://www.openslr.org/resources/30", "https://us.openslr.org/resources/30",
                   "https://openslr.elda.org/resources/30", "https://openslr.magicdatatech.com/resources/30")
SAMPLE_RATE = 24000
LICENSES = {"pathnirvana": "GPL-3.0 (non-obscene, non-offensive use only)", "openslr30": "CC-BY-SA-4.0"}
# Short ASCII voice names: they become model voice ids (--voice) and ONNX metadata.
PATHNIRVANA_VOICES = {"mettananda": "M1", "oshadi": "F1"}


# --------------------------------------------------------------------- download

def fetch(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "tiny-voca-sinhala"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as stream:
        shutil.copyfileobj(response, stream, length=1 << 20)
    return destination


def extract(archive, destination):
    """Unpack into ``destination`` without letting members escape it."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                if not (destination / member).resolve().is_relative_to(root):
                    raise ValueError(f"unsafe path in archive: {member}")
            bundle.extractall(destination)
        return
    with tarfile.open(archive) as bundle:
        try:
            bundle.extractall(destination, filter="data")
        except TypeError:                      # Python without extraction filters
            for member in bundle.getmembers():
                if not (destination / member.name).resolve().is_relative_to(root) or member.issym() or member.islnk():
                    raise ValueError(f"unsafe member in archive: {member.name}")
            bundle.extractall(destination)


def download_pathnirvana(dest):
    target = dest / "pathnirvana"
    if any(target.rglob("*.wav")) and any(target.rglob("metadata.csv")):
        print(f"{target} already has the data")
        return target
    request = urllib.request.Request(f"https://api.github.com/repos/{PATHNIRVANA_REPO}/releases/latest",
                                     headers={"User-Agent": "tiny-voca-sinhala", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.load(response)
    assets = [a for a in release.get("assets", []) if re.search(r"\.(tar(\.(gz|bz2|xz))?|tgz|zip)$", a["name"])]
    if not assets:
        raise RuntimeError(f"release {release.get('tag_name')} has no archive asset")
    asset = max(assets, key=lambda a: a["size"])
    print(f"release {release.get('tag_name')}: {asset['name']} ({asset['size'] / 1e9:.2f} GB)")
    archive = fetch(asset["browser_download_url"], dest / "downloads" / asset["name"])
    extract(archive, target)
    archive.unlink()
    if not any(target.rglob("metadata.csv")):
        fetch(f"https://raw.githubusercontent.com/{PATHNIRVANA_REPO}/{release.get('target_commitish', 'main')}/metadata.csv",
              target / "metadata.csv")
    return target


def download_pathnirvana_old(dest):
    target = dest / "pathnirvana-old"
    if (target / "old dataset" / "metadata.csv").exists():
        return target
    subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                    f"https://github.com/{PATHNIRVANA_REPO}.git", str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "sparse-checkout", "set", "--no-cone",
                    "/old dataset/wavs/", "/old dataset/metadata.csv"], check=True)
    return target


def download_openslr30(dest):
    target = dest / "openslr30"
    if (target / "si_lk.lines.txt").exists() and any(target.rglob("*.wav")):
        return target
    for mirror in OPENSLR_MIRRORS:
        try:
            lines = fetch(f"{mirror}/si_lk.lines.txt", target / "si_lk.lines.txt")
            archive = fetch(f"{mirror}/si_lk.tar.gz", dest / "downloads" / "si_lk.tar.gz")
            break
        except OSError as error:
            print(f"  {mirror} failed: {error}")
    else:
        raise RuntimeError("no OpenSLR mirror worked")
    extract(archive, target)
    archive.unlink()
    return target


# --------------------------------------------------------------------- reading

def clean_text(text):
    """Text as the speaker read it. ``-පෙ-`` (peyyāla, "and so on") is written
    but not spoken; the dataset's own script drops it the same way."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"^\s*-පෙ-\s*", "", text)
    text = re.sub(r"\s?-පෙ-", "…", text)
    text = re.sub(r"[\[{]\s?", "(", text)
    text = re.sub(r"\s?[\]}]", ")", text)
    text = re.sub(r"\(\s?\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def wav_index(root):
    return {path.stem: path for path in root.rglob("*.wav")}


def read_pathnirvana(root):
    """v2: ``id|roman|sinhala|speaker``. First release: ``id|sinhala|roman``."""
    rows, wavs = [], wav_index(root)
    for metadata in sorted(root.rglob("metadata.csv")):
        for line in metadata.read_text(encoding="utf-8").splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                identifier, _, sinhala, speaker = parts
            elif len(parts) == 3:
                # The first release (2021, 3,300 clips) names no speaker. It is Mrs. Oshadi:
                # its pitch is ~230 Hz (Ven. Mettananda ~115 Hz), and her published total
                # (4,285 clips, ~9 h) is exactly these 3,300 plus her 985 clips in v2.
                identifier, sinhala, _ = parts
                speaker = "oshadi"
            else:
                continue
            if identifier in wavs and speaker in PATHNIRVANA_VOICES:
                rows.append({"id": f"pn-{identifier}", "audio_path": wavs[identifier], "text": clean_text(sinhala),
                             "voice": PATHNIRVANA_VOICES[speaker], "origin": "pathnirvana"})
    return rows


def read_openslr30(root):
    """``si_lk.lines.txt``: Festival ``( sin_2241_0329430812 "text" )`` or TSV."""
    rows, wavs = [], wav_index(root)
    for line in (root / "si_lk.lines.txt").read_text(encoding="utf-8").splitlines():
        match = re.match(r'^\(\s*(\S+)\s+"(.*)"\s*\)\s*$', line) or re.match(r"^(\S+)\t(.+)$", line)
        if not match or match[1] not in wavs:
            continue
        speaker = match[1].split("_")[1] if match[1].count("_") >= 2 else "0"
        rows.append({"id": f"slr30-{match[1]}", "audio_path": wavs[match[1]], "text": clean_text(match[2]),
                     "voice": f"S{speaker}", "origin": "openslr30"})
    return rows


# --------------------------------------------------------------------- building

def load_audio(path, top_db):
    import librosa
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    wave, rate = sf.read(path, dtype="float32", always_2d=True)
    wave = wave.mean(axis=1)
    if rate != SAMPLE_RATE:
        from math import gcd
        factor = gcd(rate, SAMPLE_RATE)
        wave = resample_poly(wave, SAMPLE_RATE // factor, rate // factor).astype(np.float32)
    _, (start, end) = librosa.effects.trim(wave, top_db=top_db, frame_length=1024, hop_length=256)
    pad = int(0.1 * SAMPLE_RATE)                       # keep 100 ms of room at both edges
    wave = wave[max(0, start - pad):min(len(wave), end + pad)]
    peak = float(np.abs(wave).max()) if wave.size else 0.0
    if peak > 0.95:
        wave = wave * (0.95 / peak)
    return wave


def split_of(text, validation, test):
    """Deterministic split by sentence, so every voice reading it stays together."""
    bucket = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if bucket < test else "validation" if bucket < test + validation else "train"


def build(args):
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import soundfile as sf
    rows = []
    for root in args.pathnirvana or []:
        rows += read_pathnirvana(Path(root))
    for root in args.openslr30 or []:
        rows += read_openslr30(Path(root))
    if not rows:
        raise SystemExit("no rows found: check the --pathnirvana / --openslr30 directories")
    seen, unique = set(), []
    for row in rows:                                    # the old and v2 releases share clips
        if row["id"] not in seen and row["text"]:
            seen.add(row["id"])
            unique.append(row)
    rows = unique
    counts = Counter(row["voice"] for row in rows)
    print("clips per voice:", dict(counts.most_common()))
    voices = args.voices or [voice for voice, count in counts.most_common() if count >= args.min_clips]
    rows = [row for row in rows if row["voice"] in voices]
    if args.max_per_voice:
        kept = Counter()
        rows = [row for row in rows if (kept.update([row["voice"]]) or kept[row["voice"]] <= args.max_per_voice)]
    args.output.mkdir(parents=True, exist_ok=True)
    writers, buffers, shard = {}, defaultdict(list), Counter()
    seconds, rejected = defaultdict(float), Counter()

    def flush(split):
        if not buffers[split]:
            return
        table = pa.Table.from_pylist(buffers[split])
        pq.write_table(table, args.output / f"{split}-{shard[split]:05d}.parquet", compression="zstd")
        shard[split] += 1
        buffers[split].clear()

    for count, row in enumerate(rows, 1):
        try:
            wave = load_audio(row["audio_path"], args.top_db)
        except Exception as error:                     # unreadable file: skip, report
            rejected[f"unreadable: {type(error).__name__}"] += 1
            continue
        duration = len(wave) / SAMPLE_RATE
        if not args.min_seconds <= duration <= args.max_seconds:
            rejected["duration"] += 1
            continue
        stream = io.BytesIO()
        sf.write(stream, wave, SAMPLE_RATE, format="FLAC", subtype="PCM_16")
        split = split_of(row["text"], args.validation, args.test)
        buffers[split].append({"id": row["id"], "text": row["text"], "voice_id": row["voice"], "split": split,
                               "audio": {"bytes": stream.getvalue(), "path": f"{row['id']}.flac"},
                               "text_id": hashlib.sha256(row["text"].encode()).hexdigest()[:16],
                               "origin": row["origin"], "source_license": LICENSES[row["origin"]]})
        seconds[(split, row["voice"])] += duration
        if len(buffers[split]) >= args.shard_size:
            flush(split)
        if count % 500 == 0:
            print(f"  {count}/{len(rows)}", flush=True)
    for split in ("train", "validation", "test"):
        flush(split)
    config = {"speakers": voices}
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    summary = {split: {voice: round(seconds[(split, voice)] / 3600, 2) for voice in voices} for split in ("train", "validation", "test")}
    (args.output / "summary.json").write_text(json.dumps({"hours": summary, "rejected": rejected, "voices": voices}, indent=2, ensure_ascii=False) + "\n")
    print("hours per split and voice:", json.dumps(summary))
    print("rejected:", dict(rejected))
    print(f"voices: {voices}; config written to {args.output / 'config.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("download")
    get.add_argument("--source", choices=("pathnirvana", "pathnirvana-old", "openslr30"), required=True)
    get.add_argument("--dest", type=Path, default=Path("raw"))
    make = commands.add_parser("build")
    make.add_argument("--pathnirvana", nargs="*", help="Directories of Path Nirvana releases (v2 and/or old)")
    make.add_argument("--openslr30", nargs="*", help="Directory of OpenSLR-30")
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--voices", nargs="+", help="Voices to keep (default: every voice with --min-clips clips)")
    make.add_argument("--min-clips", type=int, default=300)
    make.add_argument("--max-per-voice", type=int, help="Cap clips per voice (quick experiments)")
    make.add_argument("--validation", type=float, default=0.02)
    make.add_argument("--test", type=float, default=0.02)
    make.add_argument("--min-seconds", type=float, default=1.0)
    make.add_argument("--max-seconds", type=float, default=15.0)
    make.add_argument("--top-db", type=float, default=40.0, help="Edge-silence trim threshold")
    make.add_argument("--shard-size", type=int, default=1000)
    args = parser.parse_args()
    if args.command == "download":
        source = {"pathnirvana": download_pathnirvana, "pathnirvana-old": download_pathnirvana_old,
                  "openslr30": download_openslr30}[args.source]
        print(source(args.dest))
    else:
        build(args)


if __name__ == "__main__":
    sys.exit(main())
