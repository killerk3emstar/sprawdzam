import pytest

from app.risk.smoothing import ScoreSmoother


def test_single_spike_is_not_sustained():
    smoother = ScoreSmoother(window=2, confirmations=2)
    smoother.update(0)
    smoother.update(100)
    assert smoother.smoothed == 50
    assert not smoother.sustained(80)
    smoother.update(0)
    assert not smoother.sustained(80)


def test_two_consecutive_high_readings_are_sustained():
    smoother = ScoreSmoother(window=2, confirmations=2)
    smoother.update(85)
    assert not smoother.sustained(80)  # one reading is never enough
    smoother.update(90)
    assert smoother.sustained(80)
    assert smoother.smoothed == 87.5


def test_moving_average_window():
    smoother = ScoreSmoother(window=3, confirmations=2)
    for value in (30, 60, 90):
        smoother.update(value)
    assert smoother.smoothed == 60
    smoother.update(0)
    assert smoother.smoothed == 50


def test_scores_are_clamped():
    smoother = ScoreSmoother()
    assert smoother.update(500) == 100
    assert smoother.update(-50) == 50


def test_reset_and_validation():
    smoother = ScoreSmoother()
    smoother.update(90)
    smoother.reset()
    assert smoother.smoothed == 0
    with pytest.raises(ValueError):
        ScoreSmoother(window=0)
