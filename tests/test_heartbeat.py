"""Tests for heartbeat system: interval and plateau triggers, with per-action options."""

import pytest

from coral.agent.heartbeat import (
    HeartbeatAction,
    HeartbeatRunner,
    IntervalOptions,
    PlateauOptions,
    parse_options,
    streak_for_epsilon,
)


def _make_runner(*actions: HeartbeatAction) -> HeartbeatRunner:
    return HeartbeatRunner(list(actions))


def _stall_history(n: int, *, anchor: float = 0.5) -> list[float]:
    """Build a score history that yields streak == n with epsilon == 0.

    The first eval sets the anchor; the next n evals are non-improvements
    (here, exact ties — clean for epsilon=0 plateau tests).
    """
    return [anchor] * (n + 1)


# --- Interval trigger tests ---


def test_interval_trigger_fires_on_multiple():
    action = HeartbeatAction(name="reflect", every=3, prompt="reflect now")
    runner = _make_runner(action)

    assert runner.check(local_eval_count=1, global_eval_count=1) == []
    assert runner.check(local_eval_count=2, global_eval_count=2) == []
    assert runner.check(local_eval_count=3, global_eval_count=3) == [action]
    assert runner.check(local_eval_count=4, global_eval_count=4) == []
    assert runner.check(local_eval_count=6, global_eval_count=6) == [action]


def test_interval_global_uses_global_count():
    action = HeartbeatAction(name="consolidate", every=5, prompt="", is_global=True)
    runner = _make_runner(action)

    assert runner.check(local_eval_count=1, global_eval_count=5) == [action]
    assert runner.check(local_eval_count=5, global_eval_count=3) == []


def test_interval_zero_count_never_fires():
    action = HeartbeatAction(name="reflect", every=1, prompt="")
    runner = _make_runner(action)
    assert runner.check(local_eval_count=0, global_eval_count=0) == []


# --- streak_for_epsilon tests (the helper that drives plateau detection) ---


def test_streak_for_epsilon_zero_strict_inequality():
    """epsilon=0 reproduces legacy strict-> behavior."""
    # Empty history -> 0
    assert streak_for_epsilon([], minimize=False, epsilon=0.0) == 0
    # Single score -> anchor, 0 stall
    assert streak_for_epsilon([0.5], minimize=False, epsilon=0.0) == 0
    # Strictly increasing -> 0 stall (every eval an improvement)
    assert streak_for_epsilon([0.1, 0.2, 0.3], minimize=False, epsilon=0.0) == 0
    # Flat tail -> stall counts (ties don't beat anchor)
    assert streak_for_epsilon([0.5, 0.5, 0.5], minimize=False, epsilon=0.0) == 2
    # Decreasing tail -> stall counts
    assert streak_for_epsilon([0.5, 0.4, 0.3], minimize=False, epsilon=0.0) == 2


def test_streak_for_epsilon_with_threshold():
    """epsilon>0 ignores tiny inch-ups: each step is +0.0003 over the original anchor.

    With anchor=0.500 and epsilon=0.001, threshold to reset is score > 0.501.
    None of 0.5003 / 0.5006 / 0.5009 cross it, so streak grows.
    """
    history = [0.500, 0.5003, 0.5006, 0.5009]
    assert streak_for_epsilon(history, minimize=False, epsilon=0.001) == 3
    # One real jump (above epsilon) resets streak
    history2 = [0.500, 0.5003, 0.5006, 0.502, 0.5022]
    # 0.502 > 0.500+0.001 -> reset; 0.5022 < 0.502+0.001 -> stall=1
    assert streak_for_epsilon(history2, minimize=False, epsilon=0.001) == 1


def test_streak_for_epsilon_minimize_direction():
    """For minimize tasks, smaller is better."""
    history = [0.50, 0.499, 0.498, 0.497]  # tiny improvements
    assert streak_for_epsilon(history, minimize=True, epsilon=0.01) == 3
    # Bigger drop crosses epsilon -> reset
    history2 = [0.50, 0.499, 0.40, 0.399]
    assert streak_for_epsilon(history2, minimize=True, epsilon=0.01) == 1


def test_streak_for_epsilon_none_score_counts_as_stall():
    """A None score (broken eval) applies plateau pressure but does not move the anchor."""
    history = [0.5, None, None, 0.51]
    # 0.51 > 0.5 + 0.001 -> reset; 2 None nudge streak to 2 then 3, then 0.51 resets to 0
    assert streak_for_epsilon(history, minimize=False, epsilon=0.001) == 0
    history2 = [0.5, None, None]
    assert streak_for_epsilon(history2, minimize=False, epsilon=0.001) == 2


def test_streak_for_epsilon_none_before_anchor_does_not_apply_pressure():
    """Nones before any real score have nothing to plateau against — streak starts at 0
    once the first real score arrives, regardless of how many Nones preceded it."""
    # 3 broken evals then a real score: anchor=0.5, streak resets to 0
    assert streak_for_epsilon([None, None, None, 0.5], minimize=False, epsilon=0.001) == 0
    # All Nones, no anchor ever set: streak counts them (no anchor to reset against)
    assert streak_for_epsilon([None, None, None], minimize=False, epsilon=0.001) == 3
    # None after anchor still applies pressure
    assert streak_for_epsilon([None, 0.5, None, None], minimize=False, epsilon=0.001) == 2


def test_streak_for_epsilon_anchor_only_moves_on_improvement():
    """Anchor stays put when an eval doesn't beat it by epsilon, even if score equals anchor."""
    history = [0.50, 0.50, 0.501, 0.5005, 0.50, 0.503]
    # anchor=0.5 throughout; 0.501,0.5005,0.50 all <0.5+0.01; 0.503<0.5+0.01 too -> all stall
    assert streak_for_epsilon(history, minimize=False, epsilon=0.01) == 5
    # With epsilon=0.001: 0.501 beats 0.5+0.001 -> reset (anchor=0.501),
    # 0.5005 < 0.501+0.001 -> stall=1, 0.50 < -> stall=2, 0.503 > 0.501+0.001 -> reset to 0.
    assert streak_for_epsilon(history, minimize=False, epsilon=0.001) == 0


# --- Plateau trigger tests (HeartbeatRunner) ---


def test_plateau_fires_when_stuck():
    action = HeartbeatAction(name="pivot", every=5, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # 3 stalled evals -> not enough
    assert (
        runner.check(
            local_eval_count=5,
            global_eval_count=5,
            score_history=_stall_history(3),
        )
        == []
    )
    assert (
        runner.check(
            local_eval_count=5,
            global_eval_count=5,
            score_history=_stall_history(4),
        )
        == []
    )
    # Exactly at threshold (5 stalls) -> fires
    assert runner.check(
        local_eval_count=5,
        global_eval_count=5,
        score_history=_stall_history(5),
    ) == [action]


def test_plateau_cooldown_prevents_spam():
    action = HeartbeatAction(name="pivot", every=5, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # First fire at streak=5
    assert runner.check(
        local_eval_count=5,
        global_eval_count=5,
        score_history=_stall_history(5),
    ) == [action]

    # Cooldown: no fire at streak 6,7,9
    assert (
        runner.check(
            local_eval_count=6,
            global_eval_count=6,
            score_history=_stall_history(6),
        )
        == []
    )
    assert (
        runner.check(
            local_eval_count=7,
            global_eval_count=7,
            score_history=_stall_history(7),
        )
        == []
    )
    assert (
        runner.check(
            local_eval_count=9,
            global_eval_count=9,
            score_history=_stall_history(9),
        )
        == []
    )

    # Fires again at streak=10 (5 more stalls past last-fired-at=5)
    assert runner.check(
        local_eval_count=10,
        global_eval_count=10,
        score_history=_stall_history(10),
    ) == [action]


def test_plateau_resets_on_improvement():
    action = HeartbeatAction(name="pivot", every=3, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # Stall to 3 -> fires
    assert runner.check(
        local_eval_count=3,
        global_eval_count=3,
        score_history=_stall_history(3),
    ) == [action]

    # Improvement: streak resets to 0
    history_after_improvement = _stall_history(3) + [0.7]  # 0.7 beats anchor 0.5
    assert (
        runner.check(
            local_eval_count=4,
            global_eval_count=4,
            score_history=history_after_improvement,
        )
        == []
    )

    # Stall again -> fires at fresh streak=3
    history_stalled_again = history_after_improvement + [0.7, 0.7]  # streak=2
    assert (
        runner.check(
            local_eval_count=6,
            global_eval_count=6,
            score_history=history_stalled_again,
        )
        == []
    )
    history_stalled_again = history_after_improvement + [0.7, 0.7, 0.7]  # streak=3
    assert runner.check(
        local_eval_count=7,
        global_eval_count=7,
        score_history=history_stalled_again,
    ) == [action]


def test_plateau_does_not_affect_interval_actions():
    """Plateau state should not affect interval-based actions."""
    interval = HeartbeatAction(name="reflect", every=2, prompt="reflect")
    plateau = HeartbeatAction(name="pivot", every=5, prompt="pivot", trigger="plateau")
    runner = _make_runner(interval, plateau)

    result = runner.check(
        local_eval_count=2,
        global_eval_count=2,
        score_history=_stall_history(1),
    )
    assert result == [interval]

    result = runner.check(
        local_eval_count=4,
        global_eval_count=4,
        score_history=_stall_history(5),
    )
    assert {a.name for a in result} == {"reflect", "pivot"}


def test_mixed_interval_and_plateau():
    """Both action types can coexist and trigger independently."""
    reflect = HeartbeatAction(name="reflect", every=1, prompt="reflect")
    pivot = HeartbeatAction(name="pivot", every=3, prompt="pivot", trigger="plateau")
    runner = _make_runner(reflect, pivot)

    # Eval 1: reflect fires, no plateau yet
    result = runner.check(local_eval_count=1, global_eval_count=1, score_history=[0.5])
    assert [a.name for a in result] == ["reflect"]

    # 3 stalled evals: both fire
    result = runner.check(
        local_eval_count=3,
        global_eval_count=3,
        score_history=_stall_history(3),
    )
    assert [a.name for a in result] == ["reflect", "pivot"]


def test_plateau_no_history_means_no_fire():
    """Default empty score_history means no plateau detection."""
    action = HeartbeatAction(name="pivot", every=1, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)
    assert runner.check(local_eval_count=5, global_eval_count=5) == []


# --- Per-action epsilon tests ---


def test_per_action_different_epsilons_fire_independently():
    """Two plateau actions with different epsilons evaluate the same history independently.

    History: each step is +0.0003 over the previous (and over the anchor).
    - With epsilon=0: each step beats the prior anchor -> anchor moves -> streak stays 0.
    - With epsilon=0.001: no step crosses anchor+0.001 -> streak grows to 3.
    """
    strict = HeartbeatAction(
        name="strict", every=3, prompt="", trigger="plateau", options={"epsilon": 0.0}
    )
    lax = HeartbeatAction(
        name="lax", every=3, prompt="", trigger="plateau", options={"epsilon": 0.001}
    )
    runner = _make_runner(strict, lax)

    history = [0.500, 0.5003, 0.5006, 0.5009]
    result = runner.check(
        local_eval_count=4,
        global_eval_count=4,
        score_history=history,
    )
    assert [a.name for a in result] == ["lax"]


def test_epsilon_protects_against_inch_up_pattern():
    """The pfly anti-pattern: agent gains +0.0001 per eval, plateau never fires.

    With epsilon=0.001, a slow walk from 0.6733 to 0.6753 over 8 evals
    (each +0.0003-ish, all below epsilon) should accumulate plateau streak.
    """
    pivot = HeartbeatAction(
        name="pivot", every=5, prompt="", trigger="plateau", options={"epsilon": 0.001}
    )
    runner = _make_runner(pivot)
    # 9 evals walking up from 0.6733 by ~0.0003 each — none individually crosses
    # the 0.001 epsilon over the original 0.6733 anchor for the first ~3, then
    # 0.6743 finally crosses it once.
    history = [
        0.6733,  # anchor
        0.6736,  # +0.0003 below epsilon -> stall=1
        0.6739,  # +0.0006 below epsilon -> stall=2
        0.6742,  # +0.0009 below epsilon -> stall=3
        0.6745,  # +0.0012 ABOVE epsilon -> reset, anchor=0.6745
        0.6748,  # +0.0003 -> stall=1
        0.6750,  # +0.0005 -> stall=2
        0.6752,  # +0.0007 -> stall=3
        0.6753,  # +0.0008 -> stall=4
    ]
    # streak=4 < 5 -> not yet
    assert (
        runner.check(
            local_eval_count=9,
            global_eval_count=9,
            score_history=history,
        )
        == []
    )
    # One more inch-up -> streak=5 -> fires
    history.append(0.6754)  # stall=5
    assert runner.check(
        local_eval_count=10,
        global_eval_count=10,
        score_history=history,
    ) == [pivot]


def test_epsilon_zero_is_default_legacy_behavior():
    """Default empty options means epsilon=0, i.e. strict > (legacy)."""
    action = HeartbeatAction(name="pivot", every=3, prompt="", trigger="plateau")
    assert action.options == {}
    assert parse_options("plateau", action.options).epsilon == 0.0
    runner = _make_runner(action)
    # Strictly increasing -> never plateaus
    history = [0.5, 0.500001, 0.500002, 0.500003, 0.500004]
    result = runner.check(
        local_eval_count=5,
        global_eval_count=5,
        score_history=history,
    )
    assert result == []


# --- parse_options validation tests ---


def test_parse_options_rejects_unknown_trigger():
    with pytest.raises(ValueError, match="Unknown heartbeat trigger"):
        parse_options("not_a_real_trigger", {})


def test_parse_options_rejects_unknown_keys():
    """The bug this guards against: `epslion: 0.001` silently ignored."""
    with pytest.raises(ValueError, match="Unknown options for trigger='plateau'.*epslion"):
        parse_options("plateau", {"epslion": 0.001})


def test_parse_options_interval_accepts_empty_only():
    """Interval has no options today; passing one is a typo/mistake."""
    assert isinstance(parse_options("interval", {}), IntervalOptions)
    assert isinstance(parse_options("interval", None), IntervalOptions)
    with pytest.raises(ValueError, match="Unknown options for trigger='interval'"):
        parse_options("interval", {"epsilon": 0.1})


def test_parse_options_plateau_defaults_and_overrides():
    assert parse_options("plateau", None) == PlateauOptions(epsilon=0.0)
    assert parse_options("plateau", {}) == PlateauOptions(epsilon=0.0)
    assert parse_options("plateau", {"epsilon": 0.01}) == PlateauOptions(epsilon=0.01)
