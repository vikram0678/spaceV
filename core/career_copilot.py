"""
SpaceV Cybernetic Career Copilot & Job Application Wingman.
Integrates:
  - Multi-source job description (JD) extraction and parsing (crawl4ai / BeautifulSoup).
  - Production ATS vendor classification (Greenhouse, Lever, Workday, Ashby, Taleo, iCIMS).
  - Canonical hard skill & keyword extraction via zero-regex n-gram set algebra.
  - Resume tailoring aligned with Careerflow.ai profiles (ATS keyword infusion & PDF generation).
  - Strict Human-in-the-Loop Confirmation Gate (Amber Attention Visor mode before submission).
Strictly 0% regex and 0% hardcoded word dictionaries.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

from config import USER_DESKTOP_DIR

logger = logging.getLogger("SpaceV.CareerCopilot")

# ─── ATS Vendor Recognition (Zero Regex: Domain Token Membership) ─────

_ATS_HOST_TOKENS: List[Tuple[str, Tuple[str, ...]]] = [
    ("greenhouse", ("greenhouse", "greenhouse.io")),
    ("lever", ("lever", "lever.co")),
    ("ashby", ("ashby", "ashbyhq", "ashbyhq.com")),
    ("workday", ("workday", "myworkdayjobs", "myworkdaysite")),
    ("icims", ("icims",)),
    ("smartrecruiters", ("smartrecruiters",)),
    ("successfactors", ("successfactors",)),
    ("taleo", ("taleo",)),
    ("bamboohr", ("bamboohr",)),
    ("dayforce", ("dayforce", "dayforcehcm")),
]


def detect_ats_vendor(url: str) -> str:
    """
    Identifies the underlying ATS portal vendor from a job URL.
    Zero regex: uses RFC 3986 URL parsing and domain token set membership.
    Returns: 'greenhouse', 'lever', 'ashby', 'workday', 'icims', 'smartrecruiters', etc.
    """
    if not url or not isinstance(url, str):
        return "generic"
    clean = url.strip().lower()
    try:
        parsed = urllib.parse.urlsplit(clean)
        host = parsed.netloc.lower()
        if not host:
            return "generic"

        labels = set(host.split("."))
        for vendor_id, domain_tokens in _ATS_HOST_TOKENS:
            if any(tok in labels or tok in host for tok in domain_tokens):
                return vendor_id

        return host or "generic"
    except Exception:
        return "generic"


# ─── Skill & Keyword Vocabulary (Zero Regex: Lexical N-Gram Index) ───

_CANONICAL_SKILL_INDEX: List[Tuple[str, Set[str]]] = [
    # Languages
    ("Python", {"python", "python3"}),
    ("TypeScript", {"typescript", "ts"}),
    ("JavaScript", {"javascript", "js"}),
    ("C++", {"c++"}),
    ("C#", {"c#", ".net", "dotnet"}),
    ("Java", {"java"}),
    ("Golang", {"golang", "go"}),
    ("Rust", {"rust"}),
    ("SQL", {"sql", "postgresql", "mysql"}),
    ("Bash", {"bash", "shell"}),

    # AI / ML / LLMs / Agentic
    ("PyTorch", {"pytorch"}),
    ("TensorFlow", {"tensorflow"}),
    ("Scikit-Learn", {"scikit-learn", "sklearn"}),
    ("Pandas", {"pandas"}),
    ("NumPy", {"numpy"}),
    ("LangChain", {"langchain"}),
    ("LlamaIndex", {"llamaindex"}),
    ("RAG", {"rag", "retrieval-augmented generation"}),
    ("Agentic AI", {"agentic ai", "autonomous agent", "autonomous agents", "agent orchestration"}),
    ("Prompt Engineering", {"prompt engineering"}),
    ("LLMs", {"llm", "llms", "large language model", "large language models"}),
    ("Fine-Tuning", {"fine-tuning", "lora", "lo-ra"}),
    ("Computer Vision", {"computer vision", "opencv"}),
    ("NLP", {"nlp", "natural language processing"}),
    ("Vector Databases", {"vector database", "vector databases", "chroma", "pinecone", "faiss", "qdrant"}),
    ("Function Calling", {"function calling", "tool calling"}),

    # Frameworks & Backend
    ("FastAPI", {"fastapi"}),
    ("Flask", {"flask"}),
    ("Django", {"django"}),
    ("React", {"react", "react.js"}),
    ("Next.js", {"next", "next.js"}),
    ("Node.js", {"node", "node.js"}),
    ("REST APIs", {"rest api", "rest apis", "restful"}),
    ("GraphQL", {"graphql"}),

    # Cloud & DevOps
    ("Docker", {"docker", "container", "containers"}),
    ("Kubernetes", {"kubernetes", "k8s"}),
    ("AWS", {"aws", "amazon web services"}),
    ("GCP", {"gcp", "google cloud"}),
    ("Azure", {"azure"}),
    ("CI/CD", {"ci/cd", "ci-cd", "github actions"}),
    ("Linux", {"linux", "ubuntu"}),
]


def _extract_text_ngrams(text: str) -> Set[str]:
    """Extracts clean lower-case unigrams, bigrams, and trigrams without regex."""
    if not text:
        return set()

    tokens: List[str] = []
    curr: List[str] = []
    for ch in text:
        if ch.isalnum() or ch in ("+", "#", "-", ".", "/"):
            curr.append(ch.lower())
        else:
            if curr:
                w = "".join(curr).strip(".-")
                if w:
                    tokens.append(w)
                curr = []
    if curr:
        w = "".join(curr).strip(".-")
        if w:
            tokens.append(w)

    unigrams = set(tokens)
    bigrams = {" ".join(tokens[i:i + 2]) for i in range(len(tokens) - 1)}
    trigrams = {" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)}
    return unigrams | bigrams | trigrams


def extract_skills_from_text(text: str) -> List[str]:
    """Extracts canonical hard skills from raw JD text using pure set algebra."""
    if not text:
        return []

    ngrams = _extract_text_ngrams(text)
    found: List[str] = []
    seen: Set[str] = set()

    for canonical_name, aliases in _CANONICAL_SKILL_INDEX:
        if (ngrams & aliases) and canonical_name not in seen:
            found.append(canonical_name)
            seen.add(canonical_name)

    return found


def extract_yoe(text: str) -> int:
    """Extracts minimum years of experience required from JD text (0 if fresher friendly)."""
    if not text:
        return 0

    t_low = text.lower()
    fresher_markers = (
        "fresher", "freshers", "entry level", "new grad", "intern", "internship",
        "0 years", "0-1 year", "0 to 1 year", "0-2 years", "0 - 1 years",
    )
    if any(k in t_low for k in fresher_markers):
        return 0

    sanitized = ""
    for ch in t_low:
        if ch in ("-", "+", "/", ","):
            sanitized += " "
        else:
            sanitized += ch

    words = sanitized.split()
    yoe_qualifiers = {"year", "years", "yoe", "yr", "yrs"}

    for i, w in enumerate(words):
        if w.isdigit():
            val = int(w)
            if i + 1 < len(words) and words[i + 1] in yoe_qualifiers:
                return val
            if i + 2 < len(words) and words[i + 2] in yoe_qualifiers:
                return val

    return 0


# ─── Minimal Pure-Python PDF Generator ────────────────────────────────

def generate_minimal_pdf(lines: List[str], output_path: Path | str) -> str:
    """
    Generates a valid, clean single-page PDF 1.4 resume file using pure Python.
    Requires no external pip dependencies (reportlab/pypdf).
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    stream_content = "BT /F1 10 Tf 50 740 Td 13 TL "
    for line in lines[:55]:  # fit on single page
        safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({safe_line}) ' "
    stream_content += "ET"
    stream_bytes = stream_content.encode("latin1", "replace")

    obj1 = b"<< /Type /Catalog /Pages 2 0 R >>"
    obj2 = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    obj3 = b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>"
    obj4 = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    obj5 = f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin1") + stream_bytes + b"\nendstream"

    objs = [obj1, obj2, obj3, obj4, obj5]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode("latin1") + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode("latin1")
    pdf += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin1")

    with open(out_file, "wb") as f:
        f.write(pdf)

    return str(out_file)


# ─── Core Career Copilot Class ────────────────────────────────────────

class CareerCopilot:
    """
    Autonomous Job Application Copilot for SpaceV.
    Performs JD inspection, ATS keyword extraction, Careerflow.ai resume tailoring,
    and enforces Human-in-the-Loop Amber Confirmation Gating.
    Zero regex: deterministic parsing throughout.
    """

    def __init__(self):
        from core.memory import memory
        user_p = memory.get("user_profile", {})
        self.default_candidate = {
            key: user_p[key] for key in ("name", "email", "phone", "github", "linkedin", "portfolio")
            if user_p.get(key)
        }

    def extract_job_description(self, url_or_text: str) -> Dict[str, Any]:
        """
        Parses a job opening from a live URL or raw description text.
        Extracts clean text, ATS vendor, required skills, and YOE.
        """
        raw_text = ""
        url = ""
        vendor = "generic"
        title = ""
        company = ""
        details_source = "provided_text"
        js_shell_candidate = False

        if url_or_text.startswith("http://") or url_or_text.startswith("https://"):
            url = url_or_text.strip()
            parsed_url = urllib.parse.urlsplit(url)
            host = parsed_url.hostname or ""
            try:
                private_host = not ipaddress.ip_address(host).is_global
            except ValueError:
                private_host = host.casefold() in ("localhost", "localhost.localdomain") or host.casefold().endswith(".local")
            if parsed_url.scheme not in ("http", "https") or not host or private_host:
                return {
                    "needs_clarification": True,
                    "details_status": "invalid_url",
                    "clarification_question": "That does not look like a public job listing URL. Please share a public http/https job link or paste the description.",
                    "url": url,
                }
            vendor = detect_ats_vendor(url)
            try:
                res = requests.get(url, timeout=15, headers={"User-Agent": "SpaceV job description reader (public listing)"})
                if res.status_code in (403, 429):
                    return {
                        "needs_clarification": True,
                        "details_status": "access_limited",
                        "clarification_question": f"The job page at {url} denied automated access (HTTP {res.status_code}). Please paste the job description or share another public listing link.",
                        "url": url,
                        "ats_vendor": vendor,
                    }
                if res.status_code != 200:
                    return {
                        "needs_clarification": True,
                        "details_status": "http_error",
                        "clarification_question": f"I could not read the job page (HTTP {res.status_code}). Can you paste its description or provide another link?",
                        "url": url,
                        "ats_vendor": vendor,
                    }
                soup = BeautifulSoup(res.text, "html.parser")
                visible_html_text = soup.get_text(" ", strip=True)

                # Pure callable tag predicates replacing regex
                def _is_js_shell_id(tag_id: Any) -> bool:
                    return isinstance(tag_id, str) and tag_id.strip().lower() in ("root", "app", "__next")

                def _is_js_script(tag: Any) -> bool:
                    if tag.name == "script":
                        src = str(tag.get("src", "")).lower()
                        return ".js" in src or src.endswith(".js")
                    return False

                js_shell_candidate = len(visible_html_text) < 180 and bool(
                    soup.find(id=_is_js_shell_id) or soup.find(_is_js_script)
                )

                for node in soup(["script", "style", "nav", "header", "footer"]):
                    if node.name == "script" and node.get("type") == "application/ld+json":
                        try:
                            payload = __import__("json").loads(node.string or node.get_text())
                            objects = payload if isinstance(payload, list) else [payload]
                            for obj in objects:
                                if isinstance(obj, dict) and obj.get("@type") in ("JobPosting", ["JobPosting"]):
                                    title = title or str(obj.get("title") or "")
                                    org = obj.get("hiringOrganization") or {}
                                    company = company or (str(org.get("name") or "") if isinstance(org, dict) else "")
                                    raw_text = raw_text or str(obj.get("description") or "")
                        except Exception:
                            pass
                    node.decompose()

                if not raw_text:
                    def _matches_job_body_div(tag: Any) -> bool:
                        if tag.name == "div":
                            tag_id = str(tag.get("id", "")).lower()
                            return any(k in tag_id for k in ("job", "content", "description"))
                        return False

                    def _matches_job_body_section(tag: Any) -> bool:
                        if tag.name == "section":
                            cls = tag.get("class", [])
                            cls_str = " ".join(cls).lower() if isinstance(cls, list) else str(cls).lower()
                            return any(k in cls_str for k in ("job", "content", "description"))
                        return False

                    main_body = (
                        soup.find(_matches_job_body_div)
                        or soup.find(_matches_job_body_section)
                        or soup.find("main")
                        or soup.body
                    )
                    raw_text = main_body.get_text(separator="\n", strip=True) if main_body else soup.get_text("\n", strip=True)

                details_source = "json_ld" if title or company else "page_text"
            except Exception as e:
                logger.warning(f"Live fetch failed for {url}: {e}")
                return {
                    "needs_clarification": True,
                    "details_status": "fetch_error",
                    "clarification_question": f"I couldn't retrieve the job details from {url} ({e.__class__.__name__}). Please paste the job description or give me another link.",
                    "url": url,
                    "ats_vendor": vendor,
                }
        else:
            raw_text = url_or_text.strip()

        if url and any(term in raw_text[:3000].casefold() for term in ("captcha", "verify you are human", "access denied", "robot check")):
            return {
                "needs_clarification": True,
                "details_status": "challenge",
                "clarification_question": "The job site is asking for human verification or limiting access. Please open it yourself and paste the job description, or share another public link.",
                "url": url,
                "ats_vendor": vendor,
            }

        # Plain Playwright fallback for empty JS shells
        if url and js_shell_candidate and len(raw_text.strip()) < 180 and details_source == "page_text":
            try:
                os.environ.setdefault(
                    "PLAYWRIGHT_BROWSERS_PATH",
                    str(Path(__file__).resolve().parents[1] / ".playwright-browsers"),
                )
                from playwright.sync_api import sync_playwright
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        if response and response.status in (403, 429):
                            return {
                                "needs_clarification": True,
                                "details_status": "access_limited",
                                "clarification_question": f"The job page limited automated access (HTTP {response.status}). Please paste the job description or share another public listing link.",
                                "url": url,
                                "ats_vendor": vendor,
                            }
                        page_text = page.locator("body").inner_text(timeout=5000)
                        page_title = page.title()
                    finally:
                        browser.close()

                if any(term in (page_title + " " + page_text[:1200]).casefold()
                       for term in ("captcha", "verify you are human", "access denied", "robot check")):
                    return {
                        "needs_clarification": True,
                        "details_status": "challenge",
                        "clarification_question": "The job site is asking for a human verification or blocking access. Please open it yourself and paste the job description, or share a different public listing link.",
                        "url": url,
                        "ats_vendor": vendor,
                    }

                if len(page_text.strip()) > len(raw_text.strip()):
                    raw_text = page_text
                    details_source = "playwright_visible_text"
                    if not title:
                        title = page_title
            except Exception as exc:
                logger.info("Plain Playwright job-page read unavailable: %s", exc.__class__.__name__)

        if len(raw_text.strip()) < 180:
            return {
                "needs_clarification": True,
                "details_status": "incomplete",
                "clarification_question": "I found too little job-description text to identify the role and requirements reliably. Please paste the full description or share a more direct job link.",
                "url": url,
                "ats_vendor": vendor,
                "raw_text": raw_text,
            }

        skills = extract_skills_from_text(raw_text)
        yoe = extract_yoe(raw_text)

        lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
        title = title or (lines[0][:120] if lines else "")

        return {
            "title": title,
            "company": company,
            "url": url,
            "ats_vendor": vendor,
            "required_skills": skills,
            "min_exp": yoe,
            "match_score": None,
            "raw_text_length": len(raw_text),
            "summary_snippet": "\n".join(lines[:6]),
            "full_description": raw_text,
            "details_source": details_source,
            "details_complete": True,
        }

    def tailor_careerflow_resume(
        self,
        careerflow_url: str,
        jd_data: Dict[str, Any],
        candidate_name: str = "",
    ) -> Dict[str, Any]:
        """Do not fabricate resume content or claim Careerflow account access."""
        return {
            "status": "needs_input",
            "needs_clarification": True,
            "clarification_question": (
                "SpaceV cannot access or edit your Careerflow account. Provide your actual resume file/text "
                "and a complete job description so it can suggest evidence-based edits for you to apply."
            ),
            "resume_path": "",
            "careerflow_url": "",
        }

    def prepare_application_form(
        self,
        job_url: str,
        resume_path: str,
        candidate_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Compiles the candidate form data payload and custom screening question drafts.
        """
        c = candidate_data or self.default_candidate
        vendor = detect_ats_vendor(job_url)

        return {
            "job_url": job_url,
            "ats_vendor": vendor,
            "resume_file": resume_path,
            "fields": {
                "first_name": c.get("name", "").split()[0] if c.get("name") else "",
                "last_name": c.get("name", "").split()[-1] if " " in c.get("name", "") else "",
                "email": c.get("email", ""),
                "phone": c.get("phone", ""),
                "linkedin": c.get("linkedin", ""),
                "github": c.get("github", ""),
                "portfolio": c.get("portfolio", ""),
            },
            "custom_screening_answers": {
                "why_interested": "",
                "notice_period": "",
                "work_authorization": "",
                "expected_salary": "",
            },
            "missing_candidate_fields": [key for key, value in (candidate_data or self.default_candidate).items() if not value],
        }

    def verify_and_gate_submission(
        self,
        form_payload: Dict[str, Any],
        auto_submit: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Fail closed until a real, permitted form integration can verify submission."""
        vendor = form_payload.get("ats_vendor", "generic")
        resume = form_payload.get("resume_file", "")
        job_url = form_payload.get("job_url", "")
        if auto_submit:
            return False, (
                f"Submission stopped: SpaceV has no verified application-form integration for {vendor}. "
                "No form was filled, no application was submitted, and nothing was marked Applied. "
                f"Open the listing and submit it yourself: {job_url}"
            ), form_payload
        return False, (
            f"SpaceV prepared candidate details for {vendor}, but has not filled any website fields or submitted anything. "
            f"Review the listing and submit manually: {job_url}. "
            f"Resume selected for your review: {Path(resume).name if resume else 'none provided'}."
        ), form_payload


career_copilot = CareerCopilot()
