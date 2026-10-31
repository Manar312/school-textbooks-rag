"""Cheap, dependency-free language detection for ar / en / fr (enough to pick reply language for canned messages)."""
import re

_AR = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")
_FR_WORDS = {"le", "la", "les", "des", "est", "une", "un", "quel", "quelle", "quels", "pourquoi", "comment",
             "que", "qui", "dans", "pour", "avec", "sont", "et", "du", "de", "ce", "cette", "quoi", "où"}
_EN_WORDS = {"the", "is", "are", "what", "why", "how", "of", "and", "to", "in", "for", "with", "which",
             "who", "does", "do", "can", "explain", "this", "that"}
_FR_CHARS = set("éèêàùçôîâûëïœ")


def detect_language(text: str) -> str:
    letters_ar = len(_AR.findall(text))
    letters_lat = len(_LATIN.findall(text))
    if letters_ar == 0 and letters_lat == 0:
        return "ar"
    if letters_ar >= letters_lat:
        return "ar"
    words = re.findall(r"[A-Za-zÀ-ÿ']+", text.lower())
    fr = sum(1 for w in words if w in _FR_WORDS) + sum(1 for c in text.lower() if c in _FR_CHARS)
    en = sum(1 for w in words if w in _EN_WORDS)
    return "fr" if fr > en else "en"


_SMALLTALK = {
    "thanks": (re.compile(r"^\s*(شكرا|شكراً|متشكر|تسلم|thanks?|thank you|merci)\b", re.I),
               {"ar": "العفو! لو عندك سؤال تاني في منهجك أنا موجود.", "en": "You're welcome! Ask me anything else from your books.",
                "fr": "Avec plaisir ! N'hésitez pas à poser une autre question sur vos manuels."}),
    "hello": (re.compile(r"^\s*(مرحبا|اهلا|أهلا|السلام عليكم|ازيك|هاي|hello|hi|hey|bonjour|salut)\b", re.I),
              {"ar": "أهلاً بيك! اسألني عن أي حاجة في كتب منهجك.", "en": "Hi! Ask me anything about your textbooks.",
               "fr": "Bonjour ! Posez-moi une question sur vos manuels."}),
}


def smalltalk_reply(text: str) -> str | None:
    """Short greetings / thanks get a canned reply (no retrieval, no LLM cost)."""
    if len(text.strip()) > 30:
        return None
    for pattern, replies in _SMALLTALK.values():
        if pattern.match(text):
            return replies[detect_language(text)]
    return None


NOT_FOUND_MESSAGES = {
    "ar": "مش لاقي إجابة السؤال ده في كتب منهجك. جرّب تعيد صياغة السؤال أو تحدد المادة أو الدرس.",
    "en": "I couldn't find the answer to this in your curriculum books. Try rephrasing, or name the subject or lesson.",
    "fr": "Je n'ai pas trouvé la réponse dans vos manuels. Essayez de reformuler ou précisez la matière ou la leçon.",
}
