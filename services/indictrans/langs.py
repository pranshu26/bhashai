"""Map BhashAI 2-letter language codes to IndicTrans2 FLORES-200 codes."""

FLORES = {
    "en": "eng_Latn",
    "hi": "hin_Deva",
    "mr": "mar_Deva",
    "pa": "pan_Guru",
    "bn": "ben_Beng",
    "gu": "guj_Gujr",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "kn": "kan_Knda",
    "or": "ory_Orya",
    "ur": "urd_Arab",
    "as": "asm_Beng",
    "ml": "mal_Mlym",
}


def to_flores(code: str) -> str:
    if code not in FLORES:
        raise ValueError(f"Unsupported language code for IndicTrans2: {code}")
    return FLORES[code]
