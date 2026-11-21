"""
Unit tests for core/human_actuator.py: Dual-Spline Bézier Physics & Human Actuation.
"""

from __future__ import annotations

import pytest
from core.human_actuator import (
    ActuationSpeed,
    EmergencyHaltSignal,
    HumanActuator,
    Point2D,
    TrajectoryConfig,
)


def test_point2d_euclidean_distance():
    p1 = Point2D(0.0, 0.0)
    p2 = Point2D(3.0, 4.0)
    assert p1.distance_to(p2) == 5.0


def test_bezier_trajectory_generation():
    actuator = HumanActuator()
    start = Point2D(100.0, 100.0)
    end = Point2D(500.0, 400.0)

    cfg = TrajectoryConfig(speed_profile=ActuationSpeed.NATURAL, steps=30)
    points = actuator.compute_bezier_trajectory(start, end, config=cfg)

    assert len(points) >= 30
    # First point should start at or near start
    assert math_is_close(points[0].x, start.x, abs_tol=1.0)
    assert math_is_close(points[0].y, start.y, abs_tol=1.0)
    # Final point must reach exact target
    assert points[-1].x == end.x
    assert points[-1].y == end.y


def test_instant_speed_profile_returns_endpoints():
    actuator = HumanActuator()
    start = Point2D(50.0, 50.0)
    end = Point2D(200.0, 200.0)

    cfg = TrajectoryConfig(speed_profile=ActuationSpeed.INSTANT)
    points = actuator.compute_bezier_trajectory(start, end, config=cfg)

    assert len(points) == 2
    assert points[0] == start
    assert points[1] == end


def test_emergency_halt_flag_interrupts_stream():
    actuator = HumanActuator()
    points = [Point2D(10.0, 10.0), Point2D(20.0, 20.0), Point2D(30.0, 30.0)]

    dispatched = []

    def mock_dispatch(pt: Point2D):
        dispatched.append(pt)
        if len(dispatched) == 1:
            actuator.trigger_halt()

    with pytest.raises(EmergencyHaltSignal):
        actuator.execute_stream(points, mock_dispatch, delay_per_step_s=0.0)

    assert len(dispatched) == 1


def test_corner_failsafe_halts_execution():
    actuator = HumanActuator()
    # Coordinates in top-left fail-safe corner (0, 0)
    fail_point = Point2D(0.5, 0.5)

    with pytest.raises(EmergencyHaltSignal):
        actuator.execute_stream([fail_point], lambda pt: None, delay_per_step_s=0.0)


def test_typing_delay_generation_bounds():
    actuator = HumanActuator()
    delays = actuator.generate_typing_delays(char_count=50, base_wpm=60.0)

    assert len(delays) == 50
    # Physiological typing bounds: between 15ms and 250ms
    assert all(0.015 <= d <= 0.250 for d in delays)


def math_is_close(a: float, b: float, abs_tol: float = 1.0) -> bool:
    return abs(a - b) <= abs_tol
