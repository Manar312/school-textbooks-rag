from app.core.constants import is_valid_grade
from app.services.extraction import looks_garbled
from app.services.prompts import grade_label, normalize_history, used_citation_numbers
from app.core.textutil import detect_language, smalltalk_reply


def test_language_detection():
    assert detect_language("ايه هو قانون نيوتن التاني؟") == "ar"
    assert detect_language("What is photosynthesis and why is it important?") == "en"
    assert detect_language("Pourquoi les plantes ont-elles besoin de lumière ?") == "fr"
    assert detect_language("12 + 5 = ?") == "ar"  # no letters: default


def test_smalltalk_only_for_short_greetings():
    assert smalltalk_reply("شكرا") is not None
    assert "Hi" in smalltalk_reply("hello")
    assert smalltalk_reply("hello, can you explain Newton's second law in detail please?") is None


def test_grades():
    assert is_valid_grade("primary-6") and is_valid_grade("secondary-3") and is_valid_grade("prep-1")
    assert not is_valid_grade("primary-7") and not is_valid_grade("grade-4") and not is_valid_grade("prep-0")
    assert grade_label("prep-2") == "Preparatory grade 2"


def test_history_is_normalized_for_the_api():
    msgs = [{"role": "assistant", "content": "orphan"},
            {"role": "user", "content": "q1"},  # q1 got no answer (failed turn)
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "   "}]
    out = normalize_history(msgs)
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert "q1" in out[0]["content"] and "q2" in out[0]["content"]


def test_citation_parsing_ignores_invalid_numbers():
    assert used_citation_numbers("A [1] and B [3] and C [9] and [1].", 4) == [1, 3]
    assert used_citation_numbers("no refs", 4) == []


def test_garbled_text_detection():
    assert looks_garbled("(cid:12)(cid:45) text")
    assert looks_garbled("ﺍﻠﺎﻳ" * 10)  # Arabic presentation forms: visual-order text layer
    assert not looks_garbled("النص العربي العادي سليم تماما")
    assert not looks_garbled("")
