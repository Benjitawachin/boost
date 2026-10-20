from monitor.engine import location_priority

POPULAR = "popular|s sur|2° sur|3° sur|s norte|2° norte|3° norte"
TERCERA = "3ra bandeja|3° bandeja|tercera bandeja|platea alta"
K = "k|!sin k"
TORRES = "torre|torres|terraza|terrazas|ts|tn"


def test_empty_list_accepts_any_sector():
    assert location_priority("Cualquier cosa", []) == 0


def test_priority_follows_list_order():
    prefs = [TERCERA, POPULAR]
    assert location_priority("Popular (Activo/Adherente)", prefs) == 1
    assert location_priority("3ra bandeja (SIN K) $80.500", prefs) == 0
    assert location_priority("Palcos", prefs) is None


def test_case_and_accents_from_the_stadium_map():
    assert location_priority("2° SUR", [POPULAR]) == 0
    assert location_priority("S Norte", [POPULAR]) == 0
    assert location_priority("TS 3", [TORRES]) == 0


def test_whole_words_only():
    assert location_priority("Palcos VIP S", [POPULAR]) is None
    assert location_priority("Sur1", [POPULAR]) is None
    assert location_priority("Kiosco", [K]) is None


def test_exclusion_avoids_false_k_match():
    assert location_priority("K $80.500", [K]) == 0
    assert location_priority("3ra bandeja (SIN K)", [K]) is None
    assert location_priority("3ra bandeja (SIN K)", [K, TERCERA]) == 1
