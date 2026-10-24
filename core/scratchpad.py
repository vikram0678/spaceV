"""
Production Working Memory & Task Scratchpad for SpaceV Agent.
Enables high-fidelity multi-step desktop task decomposition, dynamic checklist tracking,
intermediate variable caching (URLs, file paths, coordinates), and self-healing context.
"""
import datetime
import json
from dataclasses import asdict, dataclass, field
from typing import Any


class StepStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ScratchpadStep:
    id: int
    description: str
    status: str = StepStatus.PENDING
    action_tool: str | None = None
    result_summary: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScratchpadStep":
        return cls(**data)


class SpaceVScratchpad:
    """
    Structured working memory for SpaceV autonomous desktop execution.
    Maintains active task state across multi-step LangGraph iterations.
    """
    def __init__(self, goal: str = ""):
        self.goal: str = goal
        self.plan: list[ScratchpadStep] = []
        self.notes: dict[str, Any] = {}
        self.execution_log: list[str] = []
        self.current_step_index: int = 0
        self.is_active: bool = bool(goal)
        self.max_steps: int = 10

    def set_goal(self, goal: str):
        """Sets or updates the primary task goal. Resets checklist when goal changes."""
        clean_new = goal.strip().lower() if goal else ""
        clean_old = self.goal.strip().lower() if self.goal else ""
        if clean_old and clean_new != clean_old:
            # Goal has changed: clean up previous turn's plan checklist
            self.plan = []
            self.current_step_index = 0
        self.goal = goal
        self.is_active = bool(goal)

    def clear_plan(self):
        """Clears the active plan checklist while preserving working memory notes."""
        self.plan = []
        self.current_step_index = 0

    def create_plan(self, steps: list[str]):
        """
        Initializes an ordered plan checklist.
        The first step is automatically placed in progress.
        """
        self.plan = []
        for idx, desc in enumerate(steps[:self.max_steps], start=1):
            initial_status = StepStatus.IN_PROGRESS if idx == 1 else StepStatus.PENDING
            self.plan.append(ScratchpadStep(id=idx, description=desc.strip(), status=initial_status))
        self.current_step_index = 0
        self.is_active = len(self.plan) > 0
        self._log(f"Plan created with {len(self.plan)} steps for goal: '{self.goal}'")

    def get_current_step(self) -> ScratchpadStep | None:
        """Returns the step currently in progress."""
        if 0 <= self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None

    def advance_step(self, result: str = "", success: bool = True):
        """
        Marks current step as completed or failed and moves to next step.
        """
        curr = self.get_current_step()
        if not curr:
            return

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        curr.updated_at = ts
        curr.result_summary = str(result)[:200] if result else ""

        if success:
            curr.status = StepStatus.COMPLETED
            self._log(f"Step {curr.id} COMPLETED: {curr.description}")
        else:
            curr.status = StepStatus.FAILED
            self._log(f"Step {curr.id} FAILED: {curr.description} (Error: {curr.result_summary})")

        # Move to next step if available
        self.current_step_index += 1
        next_step = self.get_current_step()
        if next_step:
            next_step.status = StepStatus.IN_PROGRESS
            next_step.updated_at = ts
            self._log(f"Step {next_step.id} ACTIVATED: {next_step.description}")

    def record_tool_action(self, tool_name: str, args: dict[str, Any], result: str):
        """
        Records tool execution telemetry into scratchpad working memory.
        Auto-extracts intermediate variables into notes.
        """
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log(f"[{ts}] Tool {tool_name}({args}) -> {str(result)[:120]}")

        # Automatically capture intermediate artifacts
        if isinstance(args, dict):
            for k, v in args.items():
                if any(target in k.lower() for target in ["url", "path", "file", "query", "app", "name"]):
                    self.set_note(f"last_{k}", v)

        # Update current step tool tracking
        curr = self.get_current_step()
        if curr:
            curr.action_tool = tool_name
            if not curr.result_summary:
                curr.result_summary = str(result)[:150]

    def set_note(self, key: str, value: Any):
        """Saves a key-value pair to working memory blackboard."""
        self.notes[str(key)] = value

    def get_note(self, key: str, default: Any = None) -> Any:
        """Retrieves a key-value pair from working memory."""
        return self.notes.get(str(key), default)

    def has_pending_steps(self) -> bool:
        """Returns True if there are remaining incomplete steps."""
        if not self.plan:
            return False
        return any(s.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS) for s in self.plan)

    def get_progress_summary(self) -> str:
        """Returns a single line summary of progress (e.g. '2/4 steps completed')."""
        if not self.plan:
            return "No active checklist."
        completed = sum(1 for s in self.plan if s.status == StepStatus.COMPLETED)
        return f"{completed}/{len(self.plan)} steps completed"

    def format_prompt_context(self) -> str:
        """
        Generates a concise, high-signal Markdown context block to inject into the LLM prompt.
        """
        if not self.is_active and not self.notes and not self.plan:
            return ""

        lines = ["\n[AGENT SCRATCHPAD & WORKING MEMORY]"]
        if self.goal:
            lines.append(f"🎯 Objective: {self.goal}")

        if self.plan:
            lines.append(f"📋 Plan Progress ({self.get_progress_summary()}):")
            for s in self.plan:
                if s.status == StepStatus.COMPLETED:
                    icon = "✔"
                elif s.status == StepStatus.IN_PROGRESS:
                    icon = "▶"
                elif s.status == StepStatus.FAILED:
                    icon = "✖"
                elif s.status == StepStatus.SKIPPED:
                    icon = "↷"
                else:
                    icon = " "

                note_str = f" -> {s.result_summary}" if s.result_summary and s.status == StepStatus.COMPLETED else ""
                lines.append(f"  [{icon}] Step {s.id}: {s.description}{note_str}")

        if self.notes:
            lines.append("📝 Working Memory Notes:")
            for k, v in list(self.notes.items())[-5:]:  # keep top 5 most relevant notes
                lines.append(f"  • {k}: {v}")

        return "\n".join(lines)

    def _log(self, entry: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.execution_log.append(f"[{ts}] {entry}")
        if len(self.execution_log) > 50:
            self.execution_log = self.execution_log[-50:]

    def to_dict(self) -> dict[str, Any]:
        """Serializes scratchpad for LangGraph state persistence."""
        return {
            "goal": self.goal,
            "plan": [s.to_dict() for s in self.plan],
            "notes": self.notes,
            "execution_log": self.execution_log,
            "current_step_index": self.current_step_index,
            "is_active": self.is_active,
            "max_steps": self.max_steps
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SpaceVScratchpad":
        """Reconstitutes scratchpad from LangGraph state."""
        instance = cls()
        if not data or not isinstance(data, dict):
            return instance

        instance.goal = data.get("goal", "")
        instance.notes = data.get("notes", {})
        instance.execution_log = data.get("execution_log", [])
        instance.current_step_index = data.get("current_step_index", 0)
        instance.is_active = data.get("is_active", False)
        instance.max_steps = data.get("max_steps", 10)

        plan_data = data.get("plan", [])
        instance.plan = [ScratchpadStep.from_dict(item) for item in plan_data if isinstance(item, dict)]
        return instance


# Global active singleton for tool execution bindings
active_scratchpad = SpaceVScratchpad()


def scratchpad_set_plan(steps: list[str]) -> str:
    """Initializes or resets the agent scratchpad plan checklist."""
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except Exception:
            steps = [s.strip() for s in steps.split(",") if s.strip()]
    if not isinstance(steps, list):
        steps = [str(steps)]
    active_scratchpad.create_plan(steps)
    return f"Scratchpad plan initialized with {len(active_scratchpad.plan)} steps, Sir."


def scratchpad_note(key: str, value: str) -> str:
    """Stores an intermediate fact or variable in the scratchpad working memory."""
    active_scratchpad.set_note(key, value)
    return f"Recorded in scratchpad: {key} = {value}"


def scratchpad_view() -> str:
    """Returns the current state of the agent scratchpad."""
    return active_scratchpad.format_prompt_context() or "Scratchpad is currently empty, Sir."
