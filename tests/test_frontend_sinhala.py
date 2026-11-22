"""Sinhala front end. Run with TINY_VOCA_LANGUAGE=si:

    TINY_VOCA_LANGUAGE=si PYTHONPATH=src:tests python -m unittest tests.test_frontend_sinhala
"""

import os
import unittest

SINHALA = os.environ.get("TINY_VOCA_LANGUAGE") == "si"


@unittest.skipUnless(SINHALA, "set TINY_VOCA_LANGUAGE=si")
class SinhalaPureTests(unittest.TestCase):
    """No eSpeak needed."""

    def test_inventory_drives_the_model_vocabulary(self):
        from tiny_voca.config import Config
        from tiny_voca.text import SYMBOLS, SYMBOL_TO_ID, language
        self.assertEqual(language(), "si")
        self.assertEqual(Config().vocab_size, len(SYMBOLS))
        self.assertEqual(len(set(SYMBOLS)), len(SYMBOLS))
        self.assertEqual(SYMBOL_TO_ID["<pad>"], 0)

    def test_prenasal_merge(self):
        from tiny_voca.sinhala import merge
        self.assertEqual(merge([("ɐ", 1), ("ᵐ", 0), ("b", 0), ("ə", 0)]), [("ɐ", 1), ("ᵐb", 0), ("ə", 0)])
        self.assertEqual(merge([("ᵑ", 0), ("ɡ", 2)]), [("ᵑɡ", 2)])
        self.assertEqual(merge([("ᵐ", 0), ("k", 0)]), [("ᵐ", 0), ("k", 0)])

    def test_canonical_mapping(self):
        from tiny_voca.sinhala import canonical
        self.assertEqual(canonical("ʈʰ"), ("ʈʰ",))
        self.assertEqual(canonical("tʃʰə"), ("tʃʰ", "ə"))   # isolated letter, fused by eSpeak
        self.assertEqual(canonical("əʊ"), ("oː",))           # English word in Latin script
        self.assertEqual(canonical("ᵐ"), ("m",))
        self.assertIsNone(canonical("ʘ"))

    def test_parse_strips_stress_and_language_flags(self):
        from tiny_voca.sinhala import parse
        self.assertEqual(parse("ˈaː_j_u_b_ˌoː_w_ə_n s_ˈɐ_ⁿ_d_ə"),
                         [[("aː", 1), ("j", 0), ("u", 0), ("b", 0), ("oː", 2), ("w", 0), ("ə", 0), ("n", 0)],
                          [("s", 0), ("ɐ", 1), ("ⁿd", 0), ("ə", 0)]])
        self.assertEqual(parse("(en)_h_ə_(si)"), [[("h", 0), ("ə", 0)]])

    def test_normalize(self):
        from tiny_voca.sinhala import normalize
        self.assertEqual(normalize("ශ්‍රී"), "ෂ්රී")
        self.assertEqual(normalize("හරි෴"), "හරි.")

    def test_every_phone_has_an_aligner_label(self):
        from tiny_voca.align import ALIGNER_LABEL_FALLBACK
        from tiny_voca.sinhala import ALIGNER_LABELS, PHONES
        for phone, label in ALIGNER_LABELS.items():
            self.assertIn(phone, PHONES)
            self.assertEqual(ALIGNER_LABEL_FALLBACK[phone], label)

    def test_sentence_split_on_sinhala(self):
        from tiny_voca.infer import sentences
        self.assertEqual(sentences("මම ගෙදර යනවා. ඔයා එනවද? ඔව්!"), ["මම ගෙදර යනවා.", "ඔයා එනවද?", "ඔව්!"])


def _has_espeak():
    try:
        import espeakng_loader, phonemizer  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(SINHALA and _has_espeak(), "needs TINY_VOCA_LANGUAGE=si, phonemizer-fork and espeakng-loader")
class SinhalaEspeakTests(unittest.TestCase):

    def phones(self, text):
        from tiny_voca.text import phonemize
        result = phonemize(text)
        self.assertEqual(result.unknown, ())
        return " ".join(result.symbols)

    def test_words(self):
        self.assertEqual(self.phones("ආයුබෝවන්"), "<bos> aː j u b oː w ə n <eos>")
        self.assertEqual(self.phones("මම ගෙදර යනවා."), "<bos> m ɐ m ə <sp> ɡ e d ə ɹ ə <sp> j ɐ n ə w aː . <eos>")

    def test_retroflex_and_aspirates_stay_distinct(self):
        self.assertIn("ʈ", self.phones("ටොපි"))
        self.assertIn("ɖ", self.phones("ඩබල්"))
        self.assertIn("dʰ", self.phones("ඖෂධ"))

    def test_prenasalised_stops_are_one_token(self):
        self.assertEqual(self.phones("අඹ"), "<bos> ɐ ᵐb ə <eos>")
        self.assertEqual(self.phones("සඳ"), "<bos> s ɐ ⁿd ə <eos>")
        self.assertEqual(self.phones("ගඟ"), "<bos> ɡ ɐ ᵑɡ ə <eos>")

    def test_joiner_does_not_split_words(self):
        self.assertEqual(self.phones("ශ්‍රී ලංකාව"), "<bos> ʃ ɹ iː <sp> l ɐ ŋ k aː w <eos>")
        self.assertEqual(self.phones("ක්‍රමය"), self.phones("ක්රමය"))

    def test_punctuation_and_numbers(self):
        self.assertEqual(self.phones("ඔයා එනවද?"), "<bos> o j aː <sp> e n ə w ə d ə ? <eos>")
        self.assertIn("e k ə", self.phones("1"))

    def test_identity_is_stable(self):
        from tiny_voca.text import frontend_fingerprint, frontend_identity
        self.assertEqual(frontend_identity()["language"], "si")
        self.assertEqual(frontend_fingerprint(), frontend_fingerprint())


if __name__ == "__main__":
    unittest.main()
