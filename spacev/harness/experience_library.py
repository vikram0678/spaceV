"""
SpaceV Harnessing Subsystem: Domain Experience Library.
Engineered from Harness² (Google LLC 2026) for persistent, cross-session operational memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OperationalLesson:
    task_id: str
    cue: str  # The situation/trigger that activates this lesson
    lesson: str  # The operational guidance or action to perform
    evidence: str  # Log snippet or trajectory hash proving the lesson
    confidence: float = 0.95
    category: str = "general"


class ExperienceLibrary:
    """
    Persistent domain experience library:
        <root>/<domain>/INDEX.md
        <root>/<domain>/harnesses/<task_id>/EXPERIENCE.md
    """

    def __init__(self, root_dir: Path | str):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _domain_dir(self, domain: str) -> Path:
        clean_name = re.sub(r"[^\w\-]", "_", domain.lower()).strip("_") or "general"
        d = self.root / clean_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def record_lesson(self, domain: str, lesson: OperationalLesson) -> Path:
        dom_dir = self._domain_dir(domain)
        task_slug = re.sub(r"[^\w\-]", "_", lesson.task_id.lower()).strip("_")
        task_dir = dom_dir / "harnesses" / task_slug
        task_dir.mkdir(parents=True, exist_ok=True)

        exp_file = task_dir / "EXPERIENCE.md"
        content = (
            f"# Experience: {lesson.task_id}\n\n"
            f"- **Category**: {lesson.category}\n"
            f"- **Confidence**: {lesson.confidence}\n\n"
            f"## Cue\n{lesson.cue.strip()}\n\n"
            f"## Transferable Lesson\n{lesson.lesson.strip()}\n\n"
            f"## Evidence\n```\n{lesson.evidence.strip()}\n```\n"
        )
        exp_file.write_text(content, encoding="utf-8")
        self.rebuild_index(domain)
        return exp_file

    def rebuild_index(self, domain: str) -> Path:
        dom_dir = self._domain_dir(domain)
        index_file = dom_dir / "INDEX.md"
        harnesses_dir = dom_dir / "harnesses"

        entries: list[str] = []
        if harnesses_dir.is_dir():
            for task_folder in sorted(harnesses_dir.iterdir()):
                exp_file = task_folder / "EXPERIENCE.md"
                if exp_file.is_file():
                    text = exp_file.read_text(encoding="utf-8")
                    cue_match = re.search(r"## Cue\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
                    cue_snippet = cue_match.group(1).strip() if cue_match else "No cue specified"
                    entries.append(f"- **{task_folder.name}**: {cue_snippet}")

        body = (
            f"# Operational Experience Index: {domain.upper()}\n\n"
            f"Accumulated lessons for autonomous navigation in {domain}:\n\n"
            + ("\n".join(entries) if entries else "*(No prior lessons recorded)*")
            + "\n"
        )
        index_file.write_text(body, encoding="utf-8")
        return index_file

    def retrieve_relevant_lessons(self, domain: str, context_query: str) -> list[OperationalLesson]:
        dom_dir = self._domain_dir(domain)
        harnesses_dir = dom_dir / "harnesses"
        results: list[OperationalLesson] = []

        if not harnesses_dir.is_dir():
            return results

        tokens = set(re.findall(r"\w+", context_query.lower()))

        for task_folder in harnesses_dir.iterdir():
            exp_file = task_folder / "EXPERIENCE.md"
            if not exp_file.is_file():
                continue
            text = exp_file.read_text(encoding="utf-8")

            cue = re.search(r"## Cue\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
            lesson = re.search(r"## Transferable Lesson\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
            evidence = re.search(r"## Evidence\n```\n?(.*?)\n?```", text, re.DOTALL)

            cue_text = cue.group(1).strip() if cue else ""
            lesson_text = lesson.group(1).strip() if lesson else ""
            evidence_text = evidence.group(1).strip() if evidence else ""

            # Score relevance by token overlap
            cue_tokens = set(re.findall(r"\w+", cue_text.lower()))
            overlap = len(tokens.intersection(cue_tokens))

            if overlap > 0 or not tokens:
                results.append(
                    OperationalLesson(
                        task_id=task_folder.name,
                        cue=cue_text,
                        lesson=lesson_text,
                        evidence=evidence_text,
                        confidence=0.95,
                        category=domain,
                    )
                )

        return results
