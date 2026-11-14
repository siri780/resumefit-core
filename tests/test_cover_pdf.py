from app.cover_pdf import escape, letter_tex, safe_name


def test_escape_special_characters():
    assert escape("R&D 50% $5 #1 a_b") == r"R\&D 50\% \$5 \#1 a\_b"
    assert escape("a—b") == "a---b"


def test_letter_keeps_paragraphs_and_signature_line():
    tex = letter_tex("Dear X Team,\n\nPara one.\n\nSincerely,\nShirisha Gajendra")
    assert "Dear X Team," in tex
    assert "Sincerely,\\\\\nShirisha Gajendra" in tex
    assert "{{PHONE}}" in tex and "{{EMAIL}}" in tex


def test_safe_name():
    assert safe_name("Akamai Technologies, Inc.") == "Akamai_Technologies_Inc"
    assert safe_name("!!!") == "Company"
