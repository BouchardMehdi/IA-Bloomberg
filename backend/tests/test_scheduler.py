from app.scheduler.main import seconds_until_next_run


def test_scheduler_keeps_a_fixed_interval() -> None:
    assert seconds_until_next_run(interval_minutes=15, elapsed_seconds=12.5) == 887.5


def test_scheduler_waits_at_least_one_second_after_a_slow_run() -> None:
    assert seconds_until_next_run(interval_minutes=1, elapsed_seconds=75) == 1.0
