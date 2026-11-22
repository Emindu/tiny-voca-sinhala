"""Sinhala front end: Sinhala text -> eSpeak NG ``si`` phonemes with stress.

Selected with ``TINY_VOCA_LANGUAGE=si``. It follows the token convention of the
English front end (BOS/EOS, word spaces and punctuation as zero-length-capable
tokens, stress as a parallel 0/1/2 feature), so training, alignment, inference
and ONNX export work unchanged.

Phonemes come from the eSpeak NG library shipped in the ``espeakng-loader``
wheel, called through ``phonemizer-fork``. Using the wheel instead of the
system ``espeak-ng`` program pins one eSpeak build for annotation (Kaggle) and
inference (any laptop), so tokens cannot drift between the two. eSpeak NG is
GPL-3.0: fine for training and personal use, but check the licence before you
ship it inside a product.

Corrections applied before eSpeak (all measured on eSpeak NG 1.52):

* Zero-width joiners (rakaransaya, yansaya, repaya: ශ්‍රී, ක්‍ර, ද්‍ය) are removed.
  eSpeak treats the joiner as a word break and splits ශ්‍රී into ``s`` + ``ɹiː``.
* ශ is read as ෂ. eSpeak gives ``s`` for ශ inside words, but the usual reading
  is ``ʃ`` (ශ්‍රී = "shree").
* ෴ (kunddaliya) ends a sentence like a full stop.

Corrections applied to eSpeak's output:

* Prenasalised stops come out as a raised nasal plus a stop (``ᵐ`` ``b``). They
  are one sound in Sinhala (ඹ ඳ ඬ ඟ), so they are merged into one token
  (``ᵐb`` ``ⁿd`` ``ⁿɖ`` ``ᵑɡ``).
* A few isolated letters come out fused with their vowel (``tʃʰə``); units
  outside the inventory are split into inventory phones where possible.
* Words in Latin script are read by eSpeak's English voice; their English
  phones are mapped onto the closest Sinhala ones (``FALLBACK``).
"""

import hashlib
import json
import re
import threading
import unicodedata

FRONTEND_VERSION = "si-1"
ESPEAK_LANGUAGE = "si"

PAD, BOS, EOS, SP, UNK = "<pad>", "<bos>", "<eos>", "<sp>", "<unk>"
SPECIALS = (PAD, BOS, EOS, SP, UNK)
PUNCTUATION = (",", ".", "?", "!", ";", ":", '"', "'", "(", ")", "—", "…")
# Every phone eSpeak NG 1.52 emits for Sinhala script (each consonant with every
# vowel sign, independent vowels, numbers), after the merges above.
CONSONANTS = ("p", "pʰ", "b", "bʰ", "t", "tʰ", "d", "dʰ", "ʈ", "ʈʰ", "ɖ", "ɖʰ", "k", "kʰ", "ɡ", "ɡʰ",
              "tʃ", "tʃʰ", "dʒ", "dʒʰ", "ᵐb", "ⁿd", "ⁿɖ", "ᵑɡ", "m", "n", "ɳ", "ɲ", "ŋ",
              "s", "ʃ", "ʂ", "h", "f", "v", "l", "ɭ", "ɹ", "r", "j", "w")
VOWELS = ("ɐ", "ə", "aː", "i", "iː", "u", "uː", "e", "eː", "o", "oː", "æ", "æː", "aɪ", "aʊ")
PHONES = CONSONANTS + VOWELS
# Append-only: changing the order or removing a symbol invalidates checkpoints.
SYMBOLS = SPECIALS + PUNCTUATION + PHONES
SYMBOL_TO_ID = {symbol: index for index, symbol in enumerate(SYMBOLS)}
PHONE_SET = frozenset(PHONES)
PHONE_IDS = frozenset(SYMBOL_TO_ID[p] for p in PHONES) | {SYMBOL_TO_ID[UNK]}
VOWEL_SET = frozenset(VOWELS)
VOICELESS = frozenset(("p", "pʰ", "t", "tʰ", "ʈ", "ʈʰ", "k", "kʰ", "tʃ", "tʃʰ", "s", "ʃ", "ʂ", "h", "f"))
STRESS_MARKS = {"ˈ": 1, "ˌ": 2}

PRENASAL = {("ᵐ", "b"): "ᵐb", ("ⁿ", "d"): "ⁿd", ("ⁿ", "ɖ"): "ⁿɖ", ("ᵑ", "ɡ"): "ᵑɡ"}
# Phones outside the inventory: a raised nasal on its own, and English phones of
# words in Latin script. Anything else is split into inventory phones if it can
# be, otherwise it becomes <unk> and is reported.
FALLBACK = {
    "ᵐ": ("m",), "ⁿ": ("n",), "ᵑ": ("ŋ",), "a": ("ɐ",), "ɑ": ("aː",), "ɑː": ("aː",), "ɒ": ("o",), "ɔ": ("o",),
    "ɔː": ("oː",), "ʌ": ("ɐ",), "ɪ": ("i",), "ɛ": ("e",), "ɜː": ("ə",), "ɜ": ("ə",), "ɚ": ("ə",), "ᵻ": ("i",),
    "ʊ": ("u",), "oʊ": ("oː",), "əʊ": ("oː",), "eɪ": ("eː",), "ɔɪ": ("o", "i"), "iə": ("i", "ə"),
    "eə": ("e", "ə"), "ʊə": ("u", "ə"), "ɑːɹ": ("aː", "ɹ"), "ɔːɹ": ("oː", "ɹ"), "oːɹ": ("oː", "ɹ"),
    "ɪɹ": ("i", "ɹ"), "ɛɹ": ("e", "ɹ"), "ʊɹ": ("u", "ɹ"), "aɪɚ": ("aɪ", "ə"), "aɪə": ("aɪ", "ə"),
    "əl": ("ə", "l"), "n̩": ("ə", "n"), "l̩": ("ə", "l"), "θ": ("t",), "ð": ("d",), "z": ("s",),
    "ʒ": ("dʒ",), "ɾ": ("ɹ",), "ʔ": (), "x": ("k",), "ç": ("h",), "ɣ": ("ɡ",), "ʋ": ("w",),
}

# Labels of the annotation aligner (wav2vec2-lv-60-espeak-cv-ft) for inventory
# phones it lacks. Annotation only: the TTS model keeps the Sinhala phone. The
# aligner marks where a phone starts, and a prenasalised stop starts with its nasal.
ALIGNER_LABELS = {"ᵐb": "m", "ⁿd": "n", "ⁿɖ": "ɳ", "ᵑɡ": "ŋ", "dʒʰ": "dʒ"}

_JOINERS = dict.fromkeys(map(ord, "‍‌­﻿"))
_LETTERS = str.maketrans({"ශ": "ෂ", "෴": "."})


def normalize(text):
    """Sinhala-specific clean-up, applied before the shared punctuation rules."""
    text = unicodedata.normalize("NFC", text).translate(_JOINERS).translate(_LETTERS)
    return text


def merge(units):
    """Merge raised nasal + stop into one prenasalised phone. ``units`` are
    ``(phone, stress)`` pairs of one word."""
    merged, index = [], 0
    while index < len(units):
        phone, stress = units[index]
        if index + 1 < len(units) and (phone, units[index + 1][0]) in PRENASAL:
            merged.append((PRENASAL[phone, units[index + 1][0]], stress or units[index + 1][1]))
            index += 2
            continue
        merged.append((phone, stress))
        index += 1
    return merged


def split_unit(unit):
    """Split an out-of-inventory unit into inventory phones, longest first."""
    pieces, rest = [], unit
    while rest:
        for size in range(min(4, len(rest)), 0, -1):
            if rest[:size] in PHONE_SET:
                pieces.append(rest[:size])
                rest = rest[size:]
                break
        else:
            return None
    return tuple(pieces)


def canonical(phone):
    """Map one eSpeak unit to inventory phones; ``None`` when unknown."""
    if phone in PHONE_SET:
        return (phone,)
    if phone in FALLBACK:
        return FALLBACK[phone]
    stripped = "".join(c for c in unicodedata.normalize("NFD", phone) if not unicodedata.combining(c))
    for candidate in (stripped, stripped.replace("ː", "")):
        if candidate in PHONE_SET:
            return (candidate,)
        if candidate in FALLBACK:
            return FALLBACK[candidate]
    return split_unit(phone) or split_unit(stripped)


def parse(output):
    """Words of one eSpeak output line as lists of ``(phone, stress)``."""
    words = []
    for word in output.split():
        units = []
        for unit in word.split("_"):
            stress = 0
            for mark, level in STRESS_MARKS.items():
                if mark in unit:
                    stress = stress or level
                    unit = unit.replace(mark, "")
            unit = re.sub(r"\([a-z-]+\)", "", unit)
            unit = "".join(c for c in unit if unicodedata.category(c) != "Cf")
            if unit:
                units.append((unit, stress))
        if units:
            words.append(merge(units))
    return words


class Espeak:
    """eSpeak NG from the ``espeakng-loader`` wheel. libespeak-ng is not
    thread-safe, so calls are serialised."""

    _lock = threading.Lock()
    _backend = None

    @classmethod
    def backend(cls):
        if cls._backend is None:
            try:
                import espeakng_loader
                from phonemizer.backend import EspeakBackend
                from phonemizer.backend.espeak.wrapper import EspeakWrapper
            except ImportError as error:
                raise RuntimeError('the Sinhala front end needs: pip install "phonemizer-fork" "espeakng-loader"') from error
            EspeakWrapper.set_library(espeakng_loader.get_library_path())
            EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
            cls._backend = EspeakBackend(ESPEAK_LANGUAGE, with_stress=True, language_switch="remove-flags",
                                         words_mismatch="ignore")
        return cls._backend

    @classmethod
    def words(cls, pieces):
        """Phonemize text pieces (no punctuation inside). Returns one word list per piece."""
        from phonemizer.separator import Separator
        if not pieces:
            return []
        with cls._lock:
            lines = cls.backend().phonemize(list(pieces), separator=Separator(phone="_", word=" ", syllable=""), strip=True)
        return [parse(line) for line in lines]

    @classmethod
    def version(cls):
        with cls._lock:
            return ".".join(map(str, cls.backend().version()))


def identity():
    """What decides the tokens: checkpoints and annotations record its hash."""
    return {"frontend_version": FRONTEND_VERSION, "phonemizer": "espeak-ng-library", "language": "si",
            "symbols": list(SYMBOLS), "prenasal": sorted(PRENASAL.values()),
            "fallback": {key: list(value) for key, value in sorted(FALLBACK.items())},
            "normalize": hashlib.sha256(json.dumps([sorted(_JOINERS), sorted(_LETTERS.items())]).encode()).hexdigest()}
