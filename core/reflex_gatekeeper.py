"""
Cognitive Reflex Gatekeeper for SpaceV.
Enforces Kahneman System 1 (Reflex) vs System 2 (Cognitive) separation.
Prevents generative, composite, or multi-step requests from false fast-path interception.
"""
import re
from typing import ClassVar


class ReflexGatekeeper:
    """
    Evaluates whether an incoming user utterance requires high-level cognitive
    deliberation (System 2: LangGraph / Qwen Reasoner) or can safely be handled
    by zero-latency deterministic reflex execution (System 1: FastRouter).
    """

    GENERATIVE_VERBS: ClassVar[set[str]] = {
        "write", "create", "generate", "implement", "solve",
        "compose", "draft", "explain", "summarize", "analyze", "debug",
        "fix", "refactor", "develop", "build", "sing", "tell"
    }

    SPECIFIC_PROGRAM_TARGETS: ClassVar[set[str]] = {
        "anagram", "fibonacci", "reverse", "algorithm", "scraper", "calculator",
        "crawler", "game", "api", "logic", "solution", "sort", "sorting",
        "binary search", "two sum"
    }

    PROGRAMMING_LANGUAGES: ClassVar[set[str]] = {
        "python", "python3", "javascript", "typescript", "cpp", "c++",
        "java", "rust", "golang", "c#", "csharp", "sql", "html", "css",
        "bash", "shell"
    }

    EXECUTION_KEYWORDS: ClassVar[set[str]] = {
        "run", "execute", "exec", "terminal", "test", "compile"
    }

    COMPOSITE_CONJUNCTIONS: ClassVar[list[str]] = [
        " and search ", " and write ", " and find ", " and open ",
        " and make ", " and check ", " and list ",
        " then open ", " then write ", " then search ", " then run ",
        " after that "
    ]

    DEEP_RESEARCH_KEYWORDS: ClassVar[list[str]] = [
        "job application", "job applications", "jobs on", "internship",
        "internships", "vacancies", "openings", "research paper"
    ]

    @classmethod
    def should_bypass_fast_router(cls, user_prompt: str) -> bool:
        """
        Returns True if the prompt represents a cognitive/generative task that
        MUST bypass the fast router and be reasoned by the LangGraph brain.
        Returns False for trivial deterministic reflex commands.
        """
        if not user_prompt or not user_prompt.strip():
            return False

        lower = user_prompt.strip().lower()
        words = set(re.findall(r"\b[a-z0-9_+#]+\b", lower))

        # 0. Pure single-token polarity answers or conversational closures must bypass fast router
        # e.g., "no", "nope", "nah", "nevermind", "cancel", "dont", "don't"
        pure_polarity = {"no", "nope", "nah", "nevermind", "cancel", "dont", "don't"}
        clean_word = re.sub(r"[^a-z0-9']", "", lower)
        if clean_word in pure_polarity or re.match(r"^(?:no|nope|nah|nevermind|cancel|dont|don't)(?:\s+(?:thanks|thank\s+you|please|sir|spacev))?$", lower):
            return True

        # 0.1 Conversational / social queries (singing, jokes, stories) must bypass reflex media keys
        # e.g., "could you sing a song", "sing me a song", "tell me a joke"
        if re.search(r"\b(?:sing|joke|poem|story|riddle)\b", lower):
            return True

        # 0.2 Negative constraints or restrictive modifiers must bypass fast reflex execution
        # e.g., "i dont want to play any video just open thats it", "dont play anything just open youtube"
        if re.search(r"\b(?:don't|dont|do\s+not|not|never|without)\s+(?:play|run|start|watch|execute|create|open|want\s+to\s+play)\b", lower) or re.search(r"\b(?:dont|don't|do\s+not)\s+want\s+to\b", lower):
            return True

        # 0.3 Pure single-app launches or system commands must stay on Fast Path
        # e.g., "open notepad", "open vscode", "launch chrome", "open calculator"
        if re.match(r"^(?:open|launch)\s+(?:calculator|calc|notepad|chrome|paint|task\s+manager|vs\s*code|vscode|settings)$", lower):
            return False

        # 0.4 YouTube media commands (e.g. "open youtube and play top video", "play ... on youtube")
        # are single reflex intents, unless asking for code/scraping or containing negative/restrictive modifiers
        if "youtube" in words and not (words & cls.PROGRAMMING_LANGUAGES or words & cls.SPECIFIC_PROGRAM_TARGETS):
            if re.search(r"\b(?:don't|dont|do\s+not|not|never|without|just\s+open|only\s+open)\b", lower):
                return True
            return False

        # 0.5 Execution / Terminal commands require System 2 deliberation & tool orchestration
        # e.g., "yes i want to run direclty in the vscode terminal", "run reverse_number.py", "execute in terminal"
        if bool(words & cls.EXECUTION_KEYWORDS):
            return True

        # 1. Generative code tasks with specific targets or languages:
        # e.g., "write the anagram program in python3 in the vscode"
        has_specific_target = bool(words & cls.SPECIFIC_PROGRAM_TARGETS) or any(t in lower for t in cls.SPECIFIC_PROGRAM_TARGETS)
        has_language = bool(words & cls.PROGRAMMING_LANGUAGES)
        has_gen_verb = bool(words & cls.GENERATIVE_VERBS)

        # Case A: Explicit program target (e.g. "anagram program", "reverse a number")
        if has_specific_target:
            return True

        # Case B: Generative verb + Programming Language (e.g. "write python program", "code in python3")
        if (has_gen_verb or "program" in words or "script" in words) and has_language:
            return True

        # 2. Composite multi-step requests: "open chrome and search for latest job application on the ai engineer"
        if any(conj in lower for conj in cls.COMPOSITE_CONJUNCTIONS):
            # Generic editor opening ("open editor and write the code") stays on fast route if no specific program target or language
            if " and write " in lower and any(ed in lower for ed in ["editor", "notepad", "vscode"]) and not has_specific_target and not has_language:
                pass
            else:
                return True

        # 3. Deep research / job application scraping requiring multi-turn agent interaction
        if any(kw in lower for kw in cls.DEEP_RESEARCH_KEYWORDS):
            if "search" in words or "open" in words or "find" in words:
                return True

        # 4. Long prompts requiring reasoning (>20 words)
        if len(words) > 20 and "youtube" not in words:
            return True

        return False
