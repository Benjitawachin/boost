import pytest

from monitor.engine import resolve_path

DATA = {
    "data": {
        "sectores": [
            {"nombre": "Popular Norte", "disponibles": 0},
            {"nombre": "Platea Baja L", "disponibles": 4, "filas": [{"n": 1}, {"n": 2}]},
        ]
    }
}


def test_wildcard_returns_every_item():
    assert [s["nombre"] for s in resolve_path(DATA, "data.sectores[*]")] == ["Popular Norte", "Platea Baja L"]


def test_index_and_nested_field():
    assert resolve_path(DATA, "data.sectores[1].disponibles") == [4]
    assert resolve_path(DATA, "data.sectores[*].filas[*].n") == [1, 2]


def test_missing_keys_and_out_of_range_return_empty():
    assert resolve_path(DATA, "data.nada") == []
    assert resolve_path(DATA, "data.sectores[9]") == []
    assert resolve_path(DATA, "data.sectores[*].precio") == []


def test_top_level_list():
    assert resolve_path([{"a": 1}, {"a": 2}], "[*].a") == [1, 2]


def test_invalid_segment_raises():
    with pytest.raises(ValueError):
        resolve_path(DATA, "data.sec]tores")
