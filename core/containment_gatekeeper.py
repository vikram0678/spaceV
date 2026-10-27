"""
SpaceV Containment Gatekeeper & Sandbox Pre-Execution Interceptor.
Enforces Hackathon Contract #4 & #8 by ensuring external repositories (git clone),
untrusted package installations, and remote code execution scripts are deterministically
routed to isolated Celesto MicroVM sandboxes (detonate_in_sandbox) instead of executing
directly on the host operating system.

Architecture:
Uses POSIX Lexical Tokenization (shlex) and Pipeline AST Decomposition rather than
brittle string regex matching. Accurately resolves real executables (argv[0]), strips
leading environment variables, handles wrapper binaries (sudo, env), filters flag options,
and isolates chained subcommands while eliminating false positives on commands like echo/grep.
"""

from __future__ import annotations

import logging
import re
import shlex
from pathlib import Path
from typing import Any

logger = logging.getLogger("SpaceV.ContainmentGatekeeper")


class ContainmentGatekeeper:
    """
    Production-grade POSIX lexical gatekeeper and Google Magika neural inspector.
    Decomposes shell commands into AST token streams, inspects real executables,
    performs sub-millisecond deep learning byte-level inspection to detect masqueraded malware,
    and deterministically routes untrusted code to Celesto MicroVM sandboxes.
    """

    SAFE_GIT_SUBCOMMANDS = {
        "status", "log", "diff", "branch", "add", "commit", "push",
        "pull", "fetch", "show", "rev-parse", "stash", "checkout",
        "switch", "tag", "remote", "merge", "rebase", "reset"
    }

    PIPELINE_DELIMITERS = {";", "&&", "||", "|", "&"}

    FLAGS_WITH_ARGS = {"-c", "-c", "-u", "-o", "-m", "-r", "--config", "--directory", "-C"}

    DANGEROUS_BINARIES = {"elf", "pebin", "mach-o", "dex", "apk", "jar", "so"}
    DANGEROUS_SCRIPTS = {"shell", "powershell", "batch", "vbs"}
    INNOCENT_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
        ".csv", ".tsv", ".json", ".txt", ".md", ".pdf", ".xml",
        ".yaml", ".yml", ".html", ".css", ".mp3", ".mp4", ".wav"
    }

    _magika: Any = None

    @classmethod
    def get_magika(cls) -> Any:
        """Lazy-loads and caches Google Magika deep learning content-type engine."""
        if cls._magika is None:
            try:
                from magika import Magika
                cls._magika = Magika()
            except Exception as e:
                logger.warning(f"Could not initialize Google Magika neural detector: {e}")
                cls._magika = None
        return cls._magika

    @classmethod
    def inspect_file_payload(
        cls,
        target: str | Path | bytes,
        declared_name: str | None = None
    ) -> tuple[bool, str, str, float]:
        """
        Performs sub-millisecond neural deep learning content-type inspection via Google Magika.
        Inspects actual byte streams to detect binary executables and disguised malware masquerading
        under innocent file extensions (e.g. ELF/PE/Mach-O hidden in .png, .csv, .pdf, .txt).

        Returns:
            (is_dangerous, detected_label, reason, confidence_score)
        """
        file_ext = ""
        file_name = declared_name or "unknown_payload"
        raw_bytes = b""

        if isinstance(target, bytes):
            raw_bytes = target
            if declared_name:
                file_ext = Path(declared_name).suffix.lower()
        elif isinstance(target, (str, Path)):
            p = Path(target)
            if not p.exists() or not p.is_file():
                return False, "unknown", "file_not_found", 0.0
            file_name = p.name
            file_ext = p.suffix.lower()
            try:
                with open(p, "rb") as f:
                    raw_bytes = f.read(65536)
            except Exception as e:
                logger.warning(f"Could not read file {p} for neural inspection: {e}")
                return True, "unreadable", f"read_error:{e}", 0.0
        else:
            return False, "unknown", "invalid_target_type", 0.0

        if not raw_bytes:
            return False, "empty", "empty_file", 1.0

        # Heuristic header checks (absolute ground-truth signatures)
        is_elf = raw_bytes.startswith(b"\x7fELF")
        is_pe = raw_bytes.startswith(b"MZ")
        is_macho = raw_bytes.startswith((b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"))
        is_shebang = raw_bytes.startswith(b"#!")

        # Google Magika neural classification
        label = "unknown"
        mime = "application/octet-stream"
        score = 0.5
        magika = cls.get_magika()
        if magika is not None:
            try:
                res = magika.identify_bytes(raw_bytes)
                label = res.output.label.lower()
                mime = res.output.mime_type.lower()
                if hasattr(res, "score") and res.score is not None:
                    score = float(res.score)
                else:
                    score = 0.95
            except Exception as e:
                logger.warning(f"Magika identification error: {e}")

        # Enforce canonical ground truth for headers if detected
        if is_elf:
            label = "elf"
            mime = "application/x-executable"
            score = max(score, 0.99)
        elif is_pe:
            label = "pebin"
            mime = "application/x-dosexec"
            score = max(score, 0.99)
        elif is_macho:
            label = "mach-o"
            mime = "application/x-mach-binary"
            score = max(score, 0.99)

        is_binary = label in cls.DANGEROUS_BINARIES or "executable" in mime or "sharedlib" in mime
        is_script = label in cls.DANGEROUS_SCRIPTS or "shellscript" in mime or (is_shebang and ("sh" in raw_bytes[:50].decode(errors="ignore") or "bash" in raw_bytes[:50].decode(errors="ignore")))

        # Check 1: Masqueraded binary/script detection
        if file_ext in cls.INNOCENT_EXTENSIONS:
            if is_binary:
                reason = f"masqueraded_binary_{label}"
                logger.warning(
                    f"[CONTAINMENT GATEKEEPER] Neural alert: Masqueraded binary detected! "
                    f"'{file_name}' declared as '{file_ext}' but is {label} (confidence: {score:.1%})"
                )
                return True, label, reason, score
            if is_script and (is_shebang or score > 0.85):
                reason = f"masqueraded_script_{label}"
                logger.warning(
                    f"[CONTAINMENT GATEKEEPER] Neural alert: Masqueraded script detected! "
                    f"'{file_name}' declared as '{file_ext}' but contains executable {label} code."
                )
                return True, label, reason, score

        # Check 2: Direct dangerous binary executable
        if is_binary:
            return True, label, f"executable_binary_{label}", score

        return False, label, "safe", score

    @classmethod
    def _split_into_commands(cls, tokens: list[str]) -> list[list[str]]:
        """
        Splits a token stream into individual command segments separated by
        pipeline or logical delimiters (&&, ||, ;, |).
        """
        commands: list[list[str]] = []
        current: list[str] = []

        for token in tokens:
            if token in cls.PIPELINE_DELIMITERS:
                if current:
                    commands.append(current)
                    current = []
            else:
                current.append(token)

        if current:
            commands.append(current)

        return commands

    @classmethod
    def _decompose_segment(cls, tokens: list[str]) -> tuple[str, list[str], list[str]]:
        """
        Extracts (binary, positional_args, full_args) from a command segment,
        stripping environment variable assignments and execution wrappers.
        """
        if not tokens:
            return "", [], []

        # 1. Strip leading environment variable assignments (e.g. VAR=1 git ...)
        idx = 0
        while idx < len(tokens) and "=" in tokens[idx] and not tokens[idx].startswith("-"):
            idx += 1
        tokens = tokens[idx:]

        if not tokens:
            return "", [], []

        binary = tokens[0].lower()
        args = tokens[1:]

        # 2. Unwrap execution wrappers (sudo, env, nohup, xargs, time)
        if binary in ("sudo", "env", "nohup", "time") and args:
            # Skip wrapper options
            w_idx = 0
            while w_idx < len(args) and args[w_idx].startswith("-"):
                # If flag takes an argument, skip that too
                if args[w_idx] in ("-u", "-g", "-C") and w_idx + 1 < len(args):
                    w_idx += 2
                else:
                    w_idx += 1
            if w_idx < len(args):
                return cls._decompose_segment(args[w_idx:])

        # 3. Filter positional arguments from option flags
        positional: list[str] = []
        skip_next = False
        for arg in args:
            if skip_next:
                skip_next = False
                continue
            if arg in cls.FLAGS_WITH_ARGS:
                skip_next = True
                continue
            if not arg.startswith("-"):
                positional.append(arg)

        return binary, positional, args

    @classmethod
    def should_sandbox(cls, command: str) -> tuple[bool, str]:
        """
        Evaluates whether a command must be contained within a Celesto MicroVM sandbox.
        Performs POSIX lexical parsing on the full command pipeline.

        Returns:
            (should_sandbox, reason)
        """
        if not command or not isinstance(command, str):
            return False, ""

        cmd_clean = command.strip()
        if not cmd_clean:
            return False, ""

        # POSIX Lexical Tokenization
        try:
            raw_tokens = shlex.split(cmd_clean, comments=True, posix=True)
            tokens: list[str] = []
            for t in raw_tokens:
                parts = re.split(r"(&&|\|\||;|\|)", t)
                tokens.extend([p for p in parts if p])
        except ValueError:
            # Unclosed quotes or malformed syntax: Fail-Closed to microVM for safety
            logger.warning(f"[CONTAINMENT] Malformed shell syntax in: {cmd_clean[:80]} - failing closed to sandbox.")
            return True, "unparseable_shell_syntax"

        if not tokens:
            return False, ""

        # Check for remote-code execution pipe vectors (e.g. curl ... | bash, wget ... | sh)
        has_network_downloader = any(t.lower() in ("curl", "wget", "fetch") for t in tokens)
        has_shell_interpreter = any(t.lower() in ("bash", "sh", "zsh", "dash") for t in tokens)
        if "|" in tokens and has_network_downloader and has_shell_interpreter:
            logger.info(f"[CONTAINMENT] Intercepted remote code execution pipeline: {cmd_clean[:80]}")
            return True, "remote_code_exec"

        # Check 0: Pre-detonation neural file payload inspection for referenced files
        # Intercepts commands executing masqueraded binaries (e.g. 'python payload.png', 'bash data.csv', './malware.txt')
        for token in tokens:
            if token and not token.startswith("-") and token not in cls.PIPELINE_DELIMITERS:
                try:
                    tp = Path(token)
                    if tp.is_file():
                        is_dangerous, _detected_label, reason, _ = cls.inspect_file_payload(tp)
                        if is_dangerous:
                            logger.info(f"[CONTAINMENT] Neural inspection intercepted unsafe payload: {token} ({reason})")
                            return True, f"neural_inspection_flagged:{reason}"
                except (OSError, ValueError):
                    pass

        # Split into individual command segments across pipeline operators (&&, ||, ;, |)
        segments = cls._split_into_commands(tokens)

        for segment in segments:
            binary, positional, args = cls._decompose_segment(segment)
            if not binary:
                continue

            # Check 1: git clone containment
            if binary == "git":
                if positional and positional[0].lower() == "clone":
                    logger.info(f"[CONTAINMENT] Intercepted git clone: {cmd_clean[:80]}")
                    return True, "external_repo_clone"
                # If first positional argument is a safe read/commit/push subcommand, allow
                if positional and positional[0].lower() in cls.SAFE_GIT_SUBCOMMANDS:
                    continue

            # Check 2: pip install containment (untrusted packages vs requirements file)
            if binary in ("pip", "pip3") or (binary in ("python", "python3") and args and "-m" in args and "pip" in args):
                if any(p.lower() == "install" for p in positional):
                    # Check if whitelisted safe local install (-r requirements.txt or -e .)
                    is_safe_requirements = any(a in ("-r", "--requirement") for a in args)
                    is_editable_or_current = any(a in ("-e", "--editable", ".") for a in args)
                    if not is_safe_requirements and not is_editable_or_current:
                        logger.info(f"[CONTAINMENT] Intercepted untrusted package install: {cmd_clean[:80]}")
                        return True, "package_install"
                continue

            # Check 3: docker run containment
            if binary == "docker" and any(p.lower() in ("run", "exec") for p in positional):
                logger.info(f"[CONTAINMENT] Intercepted docker container execution: {cmd_clean[:80]}")
                return True, "container_exec"

            # Check 4: npm install -g containment
            if binary in ("npm", "pnpm", "yarn") and any(p.lower() in ("install", "i", "add") for p in positional):
                if any(a in ("-g", "--global") for a in args):
                    logger.info(f"[CONTAINMENT] Intercepted global npm install: {cmd_clean[:80]}")
                    return True, "global_npm_install"

            # Check 5: dynamic shell evaluation
            if binary in ("eval", "source") or (binary in ("bash", "sh") and any(a == "-c" for a in args)):
                # If nested command contains git clone or curl pipe, sandbox it
                if any("git" == t.lower() or "clone" == t.lower() or "curl" == t.lower() for t in args):
                    return True, "dynamic_shell_eval"

        return False, ""

    @classmethod
    def format_irp_card(cls, command: str, reason: str) -> str:
        """
        Formats Interactive Remediation Plan card for user decision if interactive confirmation is needed.
        """
        return (
            f"⚠️ Sir, this command involves untrusted external code ({reason}):\n"
            f"   `{command}`\n\n"
            f"   **[1]** 🛡️ Run inside Celesto Sandbox (recommended — isolated in microVM)\n"
            f"   **[2]** 💻 Run on Host (I trust this source)\n"
            f"   **[3]** ❌ Cancel\n\n"
            f"Which option, Sir?"
        )
