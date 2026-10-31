"""Egyptian school system: stages and grades."""
import re

GRADE_RE = re.compile(r"^(primary-[1-6]|prep-[1-3]|secondary-[1-3])$")
LANGUAGES = ("ar", "en", "fr")


def is_valid_grade(g: str) -> bool:
    return bool(GRADE_RE.match(g))
