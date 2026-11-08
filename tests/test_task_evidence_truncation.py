"""Ensure output truncation markers remain attached to evidence records."""

from core.task_evidence import _record_was_truncated


def test_explicit_spacev_truncation_marker_marks_record_truncated():
    text = "⚠️ ... [9000 characters / 2250 tokens truncated to protect rate limits] ..."

    assert _record_was_truncated({}, text) is True


def test_explicit_truncation_flag_marks_record_truncated():
    assert _record_was_truncated({"truncated": True}, "complete output") is True


def test_complete_record_without_marker_is_not_truncated():
    assert _record_was_truncated({}, "complete output") is False
