"""
Hardcoded tajwid rule checks.
Detects: idzhar halqi, idgham bighunnah, idgham bilaghunnah, iqlab, ikhfa haqiqi,
         qalqalah, madd thabii, madd wajib muttasil, madd jaiz munfasil,
         madd aridh lissukun, madd silah qasirah, madd silah thawilah, madd lazim,
         ghunnah, ikhfa syafawi, idgham mimi, idzhar syafawi.
Returns a list of {rule, word, description} dicts.
"""

_IDGHAM_BIGHUNNAH_LETTERS  = set("ينمو")
_IDGHAM_BILAGHUNNAH_LETTERS = set("لر")
_IDGHAM_LETTERS  = _IDGHAM_BIGHUNNAH_LETTERS | _IDGHAM_BILAGHUNNAH_LETTERS
_IKHFA_LETTERS   = set("تثجدذزسشصضطظفقك")
_IQLAB_LETTER    = "ب"
_IDZHAR_LETTERS  = set("ءهعغحخ")  # halqi letters
_QALQALAH_LETTERS = set("قطبجد")
_MADD_CHARS      = set("اوي")
_GHUNNAH_LETTERS = set("نم")
_SUKUN           = "\u0652"  # ْ
_SHADDA          = "\u0651"  # ّ
_TANWIN          = set("\u064b\u064c\u064d")  # ً ٌ ٍ
_SUPERSCRIPT_ALEF = "\u0670"  # ٰ (madd lazim marker)
_HAMZAH          = "\u0621"  # ء
_HA_DHAMIR       = "\u0647"  # ه (ha dhamir)
_FATHA           = "\u064e"
_DAMMA           = "\u064f"
_KASRA           = "\u0650"
_SMALL_WAW       = "\u0657"  # ٗ Uthmani damma on ha dhamir
_SMALL_KASRA     = "\u0656"  # ٖ Uthmani kasra on ha dhamir
# Quranic non-letter marks to strip when checking end-of-input
_QURAN_MARKS     = set(
    [chr(c) for c in range(0x0600, 0x0606)] +  # U+0600-U+0605
    ["\u06D6", "\u06D7", "\u06D8", "\u06D9", "\u06DA", "\u06DB", "\u06DC",  # Quranic annotation signs
     "\u06DD", "\u06DE", "\u06DF", "\u06E0", "\u06E1", "\u06E2", "\u06E3",
     "\u06E4", "\u06E5", "\u06E6", "\u06E7", "\u06E8", "\u06E9", "\u06EA",
     "\u06EB", "\u06EC", "\u06ED"] +
    [chr(c) for c in range(0x08D3, 0x08E3)]     # U+08D3-U+08E2
)


def _next_letter(text: str, pos: int) -> tuple[str, int]:
    """Return (char, index) of next non-diacritic, non-space letter after pos."""
    n = len(text)
    j = pos + 1
    _DIACRITICS = set(" \u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670")
    while j < n and text[j] in _DIACRITICS:
        j += 1
    return (text[j], j) if j < n else ("", -1)


_HAMZAH_FORMS = set("\u0621\u0623\u0625\u0626\u0624")  # ء أ إ ئ ؤ


def _last_letter_pos(text: str) -> int:
    """Return index of last meaningful Arabic letter, ignoring trailing Quranic marks."""
    _IGNORE = _QURAN_MARKS | set(" \u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670")
    i = len(text) - 1
    while i >= 0 and text[i] in _IGNORE:
        i -= 1
    return i


def _word_at(text: str, pos: int) -> str:
    """Return the word containing position pos."""
    start = text.rfind(" ", 0, pos)
    end = text.find(" ", pos)
    start = 0 if start == -1 else start + 1
    end = len(text) if end == -1 else end
    return text[start:end]


def check_tajwid(text: str) -> list[dict]:
    results = []
    n = len(text)

    for i, char in enumerate(text):
        next_char = text[i + 1] if i + 1 < n else ""
        next2_char = text[i + 2] if i + 2 < n else ""
        prev_char = text[i - 1] if i > 0 else ""

        # ── Noon sakinah / tanwin rules ──────────────────────────────
        is_noon_sakin = char == "ن" and (next_char == _SUKUN or next_char in _TANWIN)
        is_tanwin = char in _TANWIN

        # skip space between words to find the trigger letter
        if char == "ن" and next_char == _SUKUN:
            # look past sukun and optional space
            j = i + 2
            while j < n and text[j] == " ":
                j += 1
            trigger_char = text[j] if j < n else ""
        elif is_tanwin:
            j = i + 1
            while j < n and text[j] == " ":
                j += 1
            trigger_char = text[j] if j < n else ""
        else:
            trigger_char = next_char

        if is_noon_sakin or is_tanwin:
            if trigger_char in _IDZHAR_LETTERS:
                results.append({
                    "rule": "Idzhar Halqi",
                    "word": _word_at(text, i),
                    "description": f"noon sakinah/tanwin clear before '{trigger_char}'",
                })
            elif trigger_char in _IDGHAM_BIGHUNNAH_LETTERS:
                results.append({
                    "rule": "Idgham Bighunnah",
                    "word": _word_at(text, i),
                    "description": f"noon sakinah/tanwin merged into '{trigger_char}' with nasalization",
                })
            elif trigger_char in _IDGHAM_BILAGHUNNAH_LETTERS:
                results.append({
                    "rule": "Idgham Bilaghunnah",
                    "word": _word_at(text, i),
                    "description": f"noon sakinah/tanwin merged into '{trigger_char}' without nasalization",
                })
            elif trigger_char == _IQLAB_LETTER:
                results.append({
                    "rule": "Iqlab",
                    "word": _word_at(text, i),
                    "description": "noon sakinah/tanwin converted to meem before ب",
                })
            elif trigger_char in _IKHFA_LETTERS:
                results.append({
                    "rule": "Ikhfa Haqiqi",
                    "word": _word_at(text, i),
                    "description": f"noon sakinah/tanwin hidden before '{trigger_char}'",
                })

        # ── Qalqalah ─────────────────────────────────────────────────
        is_qalqalah_sukun = char in _QALQALAH_LETTERS and next_char == _SUKUN
        # any vowelled qalqalah letter at end of input = implied sukun at waqf
        is_qalqalah_waqf = (char in _QALQALAH_LETTERS
                            and next_char in (_TANWIN | {_FATHA, _DAMMA, _KASRA, _SHADDA})
                            and i >= _last_letter_pos(text) - 1)
        if is_qalqalah_sukun or is_qalqalah_waqf:
            results.append({
                "rule": "Qalqalah",
                "word": _word_at(text, i),
                "description": f"qalqalah letter '{char}' with sukun",
            })

        # ── Madd ─────────────────────────────────────────────────────
        # Check if char is a madd letter (ا و ي) with correct preceding vowel
        is_madd_alef = char == "\u0627" and prev_char == _FATHA
        is_madd_waw  = char == "\u0648" and prev_char == _DAMMA
        is_madd_ya   = char == "\u064a" and prev_char == _KASRA

        if is_madd_alef or is_madd_waw or is_madd_ya:
            next_letter, next_letter_idx = _next_letter(text, i)
            # strip silent alef after waw (e.g. قُوا — the ا is orthographic, not a letter)
            if (is_madd_waw or is_madd_alef) and next_letter == "\u0627":
                next_letter, next_letter_idx = _next_letter(text, next_letter_idx)
            # at word end = nothing follows except spaces/end
            rest = text[i + 1:].lstrip("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652")
            at_word_end = (not rest or rest[0] == " ")

            if next_letter in _HAMZAH_FORMS:
                same_word = " " not in text[i + 1:next_letter_idx]
                if same_word:
                    results.append({
                        "rule": "Madd Wajib Muttasil",
                        "word": _word_at(text, i),
                        "description": "madd letter + hamzah in same word (4-5 harakat)",
                    })
                else:
                    results.append({
                        "rule": "Madd Jaiz Munfasil",
                        "word": _word_at(text, i),
                        "description": "madd letter + hamzah in next word (2-5 harakat)",
                    })
            elif at_word_end and i >= _last_letter_pos(text) - 2:
                # Aridh Lissukun only at end of entire input (last word)
                results.append({
                    "rule": "Madd Aridh Lissukun",
                    "word": _word_at(text, i),
                    "description": "madd letter at end of recitation — pause here (2-6 harakat)",
                })
            else:
                results.append({
                    "rule": "Madd Thabii",
                    "word": _word_at(text, i),
                    "description": "natural madd — no hamzah or sukun after (2 harakat)",
                })

        # Madd Lazim — superscript alef ٰ
        elif char == _SUPERSCRIPT_ALEF:
            results.append({
                "rule": "Madd Lazim",
                "word": _word_at(text, i),
                "description": "madd lazim — superscript alef, must be lengthened (6 harakat)",
            })

        # Madd Silah — ha dhamir with vowel (damma/kasra on the ha itself)
        elif char == _HA_DHAMIR and next_char in (_DAMMA, _KASRA, _SMALL_WAW, _SMALL_KASRA):
            next_letter, _ = _next_letter(text, i)
            if next_letter in _HAMZAH_FORMS:
                results.append({
                    "rule": "Madd Silah Thawilah",
                    "word": _word_at(text, i),
                    "description": "ha dhamir followed by hamzah (4-5 harakat)",
                })
            elif next_letter != "":
                results.append({
                    "rule": "Madd Silah Qasirah",
                    "word": _word_at(text, i),
                    "description": "ha dhamir not followed by hamzah (2 harakat)",
                })

        # ── Ghunnah ──────────────────────────────────────────────────
        if char in _GHUNNAH_LETTERS and (next_char == _SHADDA or next2_char == _SHADDA):
            results.append({
                "rule": "Ghunnah",
                "word": _word_at(text, i),
                "description": f"'{char}' with shadda — nasalization required",
            })

        # ── Meem sakinah rules ───────────────────────────────────────
        if char == "م" and next_char == _SUKUN:
            # find trigger letter past sukun and optional space
            j = i + 2
            while j < n and text[j] == " ":
                j += 1
            trigger = text[j] if j < n else ""

            if trigger == "ب":
                results.append({
                    "rule": "Ikhfa Syafawi",
                    "word": _word_at(text, i),
                    "description": "meem sakinah hidden before ب",
                })
            elif trigger == "م":
                results.append({
                    "rule": "Idgham Mimi",
                    "word": _word_at(text, i),
                    "description": "meem sakinah merged into meem",
                })
            elif trigger != "":
                results.append({
                    "rule": "Idzhar Syafawi",
                    "word": _word_at(text, i),
                    "description": f"meem sakinah clear before '{trigger}'",
                })

    return results
