"""
Autonomous Timers and Reminders Scheduler Engine for SpaceV.
Manages background countdown timers, alarms, and voice notifications.
"""
import time
import threading
import datetime
from typing import List, Dict, Any, Callable, Optional

class TimerItem:
    def __init__(self, timer_id: str, total_seconds: float, label: str, callback: Optional[Callable] = None):
        self.timer_id = timer_id
        self.total_seconds = total_seconds
        self.label = label
        self.callback = callback
        self.start_time = time.time()
        self.end_time = self.start_time + total_seconds
        self.is_active = True
        self._thread_timer = threading.Timer(total_seconds, self._on_timeout)
        self._thread_timer.daemon = True
        self._thread_timer.start()

    def _on_timeout(self):
        if self.is_active:
            self.is_active = False
            if callable(self.callback):
                try:
                    self.callback(self.label, self.total_seconds)
                except Exception as e:
                    print(f"[Scheduler] Error executing timer callback: {e}")

    def cancel(self):
        self.is_active = False
        self._thread_timer.cancel()

    @property
    def remaining_seconds(self) -> float:
        rem = self.end_time - time.time()
        return max(0.0, rem)

class SchedulerEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SchedulerEngine, cls).__new__(cls)
            cls._instance._timers: Dict[str, TimerItem] = {}
            cls._instance._counter = 1
            cls._instance.on_timer_expired = None # Global callback for UI
        return cls._instance

    def set_timer(self, seconds: float, label: str = "Timer", callback: Optional[Callable] = None) -> str:
        """
        Creates and starts a new countdown timer.
        """
        timer_id = f"T_{self._counter}"
        self._counter += 1

        def _handle_expired(lbl, dur):
            if timer_id in self._timers:
                del self._timers[timer_id]
            # Trigger item callback
            if callable(callback):
                callback(lbl, dur)
            # Trigger global scheduler callback (for UI & TTS)
            if callable(self.on_timer_expired):
                try:
                    self.on_timer_expired(lbl, dur)
                except Exception as e:
                    print(f"[Scheduler] Global callback error: {e}")

        item = TimerItem(timer_id, seconds, label, callback=_handle_expired)
        self._timers[timer_id] = item
        
        mins = round(seconds / 60, 1)
        dur_str = f"{int(seconds)} seconds" if seconds < 60 else f"{mins} minute(s)"
        return f"Timer '{label}' set for {dur_str}, Sir."

    def list_timers(self) -> List[Dict[str, Any]]:
        """Returns list of currently active countdown timers."""
        active = []
        for tid, t in list(self._timers.items()):
            if t.is_active and t.remaining_seconds > 0:
                rem_m = int(t.remaining_seconds // 60)
                rem_s = int(t.remaining_seconds % 60)
                active.append({
                    "id": tid,
                    "label": t.label,
                    "remaining": f"{rem_m}m {rem_s}s" if rem_m > 0 else f"{rem_s}s"
                })
        return active

    def cancel_all(self):
        for t in self._timers.values():
            t.cancel()
        self._timers.clear()

scheduler = SchedulerEngine()
