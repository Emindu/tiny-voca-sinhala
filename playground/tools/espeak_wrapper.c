// Minimal eSpeak NG API for the browser: initialise, select a voice, text -> IPA phonemes,
// called exactly as phonemizer-fork calls it (espeak_TextToPhonemes, UTF-8 in, IPA with '_' between phones).
#include <stdlib.h>
#include <string.h>
#include <espeak-ng/speak_lib.h>

static char *out = NULL;
static size_t cap = 0;

__attribute__((export_name("ev_alloc"))) void *ev_alloc(size_t n) { return malloc(n); }
__attribute__((export_name("ev_free"))) void ev_free(void *p) { free(p); }

__attribute__((export_name("ev_init"))) int ev_init(const char *path) {
    return espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, path, 0);
}

__attribute__((export_name("ev_voice"))) int ev_voice(const char *name) {
    return espeak_SetVoiceByName(name);
}

static void append(const char *s, size_t n) {
    size_t len = out ? strlen(out) : 0;
    if (len + n + 2 > cap) {
        cap = (len + n + 2) * 2;
        out = realloc(out, cap);
        if (len == 0) out[0] = 0;
    }
    memcpy(out + len, s, n);
    out[len + n] = 0;
}

// Same loop as phonemizer's wrapper: call until the text pointer is NULL and join the pieces with ' '.
__attribute__((export_name("ev_phonemes"))) const char *ev_phonemes(const char *text) {
    const void *ptr = text;
    int mode = ('_' << 8) | 0x02;
    int first = 1;
    if (out) out[0] = 0; else append("", 0);
    while (ptr != NULL) {
        const char *p = espeak_TextToPhonemes(&ptr, espeakCHARS_UTF8, mode);
        if (p && p[0]) {           // phonemizer appends only non-empty results
            if (!first) append(" ", 1);
            append(p, strlen(p));
            first = 0;
        }
    }
    return out;
}

// soundicon.c needs tmpnam when mkstemp is missing; sound icons are never used for phonemes.
char *tmpnam(char *s) { (void)s; return NULL; }
