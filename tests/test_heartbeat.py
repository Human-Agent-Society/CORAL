"""Tests for heartbeat system: interval and plateau triggers."""

from coral.agent.heartbeat import HeartbeatAction, HeartbeatRunner


def _make_runner(*actions: HeartbeatAction) -> HeartbeatRunner:
    return HeartbeatRunner(list(actions))


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

    # local=1 but global=5 -> should fire (global action)
    assert runner.check(local_eval_count=1, global_eval_count=5) == [action]
    # local=5 but global=3 -> should NOT fire
    assert runner.check(local_eval_count=5, global_eval_count=3) == []


def test_interval_zero_count_never_fires():
    action = HeartbeatAction(name="reflect", every=1, prompt="")
    runner = _make_runner(action)
    assert runner.check(local_eval_count=0, global_eval_count=0) == []


# --- Plateau trigger tests ---

def test_plateau_fires_when_stuck():
    action = HeartbeatAction(name="pivot", every=5, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # Not stuck long enough
    assert runner.check(local_eval_count=5, global_eval_count=5, evals_since_improvement=3) == []
    assert runner.check(local_eval_count=5, global_eval_count=5, evals_since_improvement=4) == []

    # Exactly at threshold
    assert runner.check(local_eval_count=5, global_eval_count=5, evals_since_improvement=5) == [action]


def test_plateau_cooldown_prevents_spam():
    action = HeartbeatAction(name="pivot", every=5, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # First fire at 5
    assert runner.check(local_eval_count=5, global_eval_count=5, evals_since_improvement=5) == [action]

    # Should NOT fire again at 6, 7, 8, 9 (cooldown)
    assert runner.check(local_eval_count=6, global_eval_count=6, evals_since_improvement=6) == []
    assert runner.check(local_eval_count=7, global_eval_count=7, evals_since_improvement=7) == []
    assert runner.check(local_eval_count=9, global_eval_count=9, evals_since_improvement=9) == []

    # Fires again at 10 (5 more stalled evals since last fire)
    assert runner.check(local_eval_count=10, global_eval_count=10, evals_since_improvement=10) == [action]


def test_plateau_resets_on_improvement():
    action = HeartbeatAction(name="pivot", every=3, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # Stall to 3 -> fires
    assert runner.check(local_eval_count=3, global_eval_count=3, evals_since_improvement=3) == [action]

    # Agent improves (evals_since_improvement resets to 0)
    assert runner.check(local_eval_count=4, global_eval_count=4, evals_since_improvement=0) == []

    # Stall again from scratch -> fires at 3 again
    assert runner.check(local_eval_count=5, global_eval_count=5, evals_since_improvement=1) == []
    assert runner.check(local_eval_count=6, global_eval_count=6, evals_since_improvement=2) == []
    assert runner.check(local_eval_count=7, global_eval_count=7, evals_since_improvement=3) == [action]


def test_plateau_does_not_affect_interval_actions():
    """Plateau state should not affect interval-based actions."""
    interval = HeartbeatAction(name="reflect", every=2, prompt="reflect")
    plateau = HeartbeatAction(name="pivot", every=5, prompt="pivot", trigger="plateau")
    runner = _make_runner(interval, plateau)

    result = runner.check(local_eval_count=2, global_eval_count=2, evals_since_improvement=1)
    assert result == [interval]

    result = runner.check(local_eval_count=4, global_eval_count=4, evals_since_improvement=5)
    assert set(a.name for a in result) == {"reflect", "pivot"}


def test_mixed_interval_and_plateau():
    """Both action types can coexist and trigger independently."""
    reflect = HeartbeatAction(name="reflect", every=1, prompt="reflect")
    pivot = HeartbeatAction(name="pivot", every=3, prompt="pivot", trigger="plateau")
    runner = _make_runner(reflect, pivot)

    # Eval 1: reflect fires (every=1), no plateau yet
    result = runner.check(local_eval_count=1, global_eval_count=1, evals_since_improvement=0)
    assert [a.name for a in result] == ["reflect"]

    # Eval 3: reflect fires, pivot fires (3 stalled evals)
    result = runner.check(local_eval_count=3, global_eval_count=3, evals_since_improvement=3)
    assert [a.name for a in result] == ["reflect", "pivot"]


def test_plateau_default_evals_since_improvement():
    """When evals_since_improvement is not passed (default 0), plateau never fires."""
    action = HeartbeatAction(name="pivot", every=1, prompt="pivot!", trigger="plateau")
    runner = _make_runner(action)

    # Default evals_since_improvement=0, should never fire
    assert runner.check(local_eval_count=5, global_eval_count=5) == []
