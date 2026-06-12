from backend.data.fetchers.results import name_to_code, _norm


def test_exact_names():
    assert name_to_code("France") == "fr"
    assert name_to_code("Brazil") == "br"


def test_diacritic_tolerant_curacao():
    # martj42 spells it with a cedilla; the ASCII alias must still resolve.
    assert name_to_code("Curaçao") == "cw"
    assert name_to_code("Curacao") == "cw"


def test_diacritic_tolerant_turkiye():
    assert name_to_code("Türkiye") == "tr"
    assert name_to_code("Turkey") == "tr"


def test_unknown_returns_none():
    assert name_to_code("Atlantis") is None
    assert name_to_code("") is None


def test_norm_strips_accents_and_case():
    assert _norm("Curaçao") == "curacao"
    assert _norm("  FRANCE ") == "france"
