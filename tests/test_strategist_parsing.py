import pytest

from optiflow.agents.strategist import coerce_plan, normalize_name


def test_parses_fenced_json_with_prose_around_it():
    text = 'Here is the plan:\n```json\n{"strategies": [{"name": "tiling", "rationale": "r", "confidence": 0.7}], "flags": ["-O3"]}\n```\nDone.'
    plan = coerce_plan(text, attempt=2)
    assert plan.attempt == 2 and plan.strategies[0].name == "tiling" and plan.flags == ["-O3"]


@pytest.mark.parametrize("given,expected", [
    ("loop_interchange", "interchange"), ("Loop Tiling", "tiling"), ("cache-blocking", "tiling"),
    ("vectorization", "vectorize"), ("AoS to SoA", "soa"), ("aos_to_soa", "soa"),
    ("memoization", "memoize"), ("compiler flags", "flags"), ("algorithm_change", "algorithmic"),
    ("magic", None),
])
def test_strategy_aliases(given, expected):
    assert normalize_name(given) == expected


def test_unknown_strategies_are_dropped_but_known_ones_kept():
    plan = coerce_plan('{"strategies": [{"name": "magic"}, {"name": "unrolling", "confidence": 3}]}', 1)
    assert [s.name for s in plan.strategies] == ["unroll"]
    assert plan.strategies[0].confidence == 1.0  # clamped


def test_flags_given_as_string_are_split():
    plan = coerce_plan('{"strategies": [{"name": "flags"}], "flags": "-O3 -march=native"}', 1)
    assert plan.flags == ["-O3", "-march=native"]


@pytest.mark.parametrize("text", ["no json here", '{"strategies": []}', '{"strategies": [{"name": "magic"}]}', "{not json}"])
def test_unusable_answers_raise_value_error(text):
    with pytest.raises(ValueError):
        coerce_plan(text, 1)
