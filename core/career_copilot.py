"""
SpaceV Cybernetic Career Copilot & Job Application Wingman.
Integrates:
  - Multi-source job description (JD) extraction and parsing (crawl4ai / BeautifulSoup).
  - Production ATS vendor classification (Greenhouse, Lever, Workday, Ashby, Taleo, iCIMS).
  - Canonical hard skill & keyword extraction (ported from eto/career-ops/skill-extract.mjs).
  - Resume tailoring aligned with Careerflow.ai profiles (ATS keyword infusion & PDF generation).
  - Strict Human-in-the-Loop Confirmation Gate (Amber Attention Visor mode before submission).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from config import USER_DESKTOP_DIR

logger = logging.getLogger("SpaceV.CareerCopilot")

# ─── ATS Vendor Patterns (from eto/career-ops/ats-vendor.mjs) ─────────

ATS_HOST_PATTERNS: List[Tuple[str, str]] = [
    ("greenhouse", "greenhouse.io"),
    ("lever", "lever.co"),
    ("ashby", "ashbyhq.com"),
    ("workday", "myworkdayjobs.com"),
    ("workday", "myworkdaysite.com"),
    ("icims", "icims.com"),
    ("smartrecruiters", "smartrecruiters.com"),
    ("successfactors", "successfactors.com"),
    ("taleo", "taleo.net"),
    ("bamboohr", "bamboohr.com"),
    ("dayforce", "dayforcehcm.com"),
]


def detect_ats_vendor(url: str) -> str:
    """
    Identifies the underlying ATS portal vendor from a job URL.
    Returns: 'greenhouse', 'lever', 'ashby', 'workday', 'icims', 'smartrecruiters', etc.
    """
    if not url or not isinstance(url, str):
        return "generic"
    clean = url.strip().lower()
    try:
        parsed = urllib.parse.urlparse(clean)
        host = parsed.netloc.lower()
        for vendor_id, pattern in ATS_HOST_PATTERNS:
            if host == pattern or host.endswith(f".{pattern}") or pattern in host:
                return vendor_id
        if "greenhouse" in clean:
            return "greenhouse"
        if "lever" in clean:
            return "lever"
        if "workday" in clean:
            return "workday"
        if "ashby" in clean:
            return "ashby"
        return host or "generic"
    except Exception:
        return "generic"


# ─── Skill & Keyword Vocabulary (from eto/career-ops/skill-extract.mjs) ─

SKILL_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # Languages
    ("Python", re.compile(r"\bpython(?:3)?\b", re.I)),
    ("TypeScript", re.compile(r"\btypescript\b|\bts\b", re.I)),
    ("JavaScript", re.compile(r"\bjavascript\b|\bjs\b", re.I)),
    ("C++", re.compile(r"\bc\+\+\b", re.I)),
    ("C#", re.compile(r"\bc#\b|\b\.net\b", re.I)),
    ("Java", re.compile(r"\bjava\b", re.I)),
    ("Golang", re.compile(r"\bgolang\b|\bgo\b", re.I)),
    ("Rust", re.compile(r"\brust\b", re.I)),
    ("SQL", re.compile(r"\bsql\b|\bpostgresql\b|\bmysql\b", re.I)),
    ("Bash", re.compile(r"\bbash\b|\bshell\b", re.I)),

    # AI / ML / LLMs / Agentic
    ("PyTorch", re.compile(r"\bpytorch\b", re.I)),
    ("TensorFlow", re.compile(r"\btensorflow\b", re.I)),
    ("Scikit-Learn", re.compile(r"\bscikit-learn\b|\bsklearn\b", re.I)),
    ("Pandas", re.compile(r"\bpandas\b", re.I)),
    ("NumPy", re.compile(r"\bnumpy\b", re.I)),
    ("LangChain", re.compile(r"\blangchain\b", re.I)),
    ("LlamaIndex", re.compile(r"\bllamaindex\b", re.I)),
    ("RAG", re.compile(r"\brag\b|\bretrieval-augmented generation\b", re.I)),
    ("Agentic AI", re.compile(r"\bagentic\s+ai\b|\bautonomous\s+agents?\b|\bagent\s+orchestration\b", re.I)),
    ("Prompt Engineering", re.compile(r"\bprompt\s+engineering\b", re.I)),
    ("LLMs", re.compile(r"\bllms?\b|\blarge\s+language\s+models?\b", re.I)),
    ("Fine-Tuning", re.compile(r"\bfine-tuning\b|\blo-?ra\b", re.I)),
    ("Computer Vision", re.compile(r"\bcomputer\s+vision\b|\bopencv\b", re.I)),
    ("NLP", re.compile(r"\bnlp\b|\bnatural\s+language\s+processing\b", re.I)),
    ("Vector Databases", re.compile(r"\bvector\s+databases?\b|\bchroma\b|\bpinecone\b|\bfaiss\b|\bqdrant\b", re.I)),
    ("Function Calling", re.compile(r"\bfunction\s+calling\b|\btool\s+calling\b", re.I)),

    # Frameworks & Backend
    ("FastAPI", re.compile(r"\bfastapi\b", re.I)),
    ("Flask", re.compile(r"\bflask\b", re.I)),
    ("Django", re.compile(r"\bdjango\b", re.I)),
    ("React", re.compile(r"\breact(?:\.js)?\b", re.I)),
    ("Next.js", re.compile(r"\bnext(?:\.js)?\b", re.I)),
    ("Node.js", re.compile(r"\bnode(?:\.js)?\b", re.I)),
    ("REST APIs", re.compile(r"\brest\s+apis?\b|\brestful\b", re.I)),
    ("GraphQL", re.compile(r"\bgraphql\b", re.I)),

    # Cloud & DevOps
    ("Docker", re.compile(r"\bdocker\b|\bcontainers?\b", re.I)),
    ("Kubernetes", re.compile(r"\bkubernetes\b|\bk8s\b", re.I)),
    ("AWS", re.compile(r"\baws\b|\bamazon\s+web\s+services\b", re.I)),
    ("GCP", re.compile(r"\bgcp\b|\bgoogle\s+cloud\b", re.I)),
    ("Azure", re.compile(r"\bazure\b", re.I)),
    ("CI/CD", re.compile(r"\bci/cd\b|\bgithub\s+actions\b", re.I)),
    ("Linux", re.compile(r"\blinux\b|\bubuntu\b", re.I)),
]


def extract_skills_from_text(text: str) -> List[str]:
    """Extracts canonical hard skills from raw JD text."""
    if not text:
        return []
    found: List[str] = []
    seen: set[str] = set()
    for canonical_name, pattern in SKILL_PATTERNS:
        if pattern.search(text) and canonical_name not in seen:
            found.append(canonical_name)
            seen.add(canonical_name)
    return found


def extract_yoe(text: str) -> int:
    """Extracts minimum years of experience required from JD text (0 if fresher friendly)."""
    if not text:
        return 0
    t_low = text.lower()
    if any(k in t_low for k in ["fresher", "entry level", "new grad", "intern", "internship", "0 years", "0-1 year", "0 to 1 year"]):
        return 0
    m = re.search(r"\b(\d+)\s*\+?\s*(?:-\s*\d+)?\s*(?:years?|yoe|yrs?)\b", t_low)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 0
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
            parsed_url = urllib.parse.urlparse(url)
            host = parsed_url.hostname or ""
            try:
                private_host = not ipaddress.ip_address(host).is_global
            except ValueError:
                private_host = host.casefold() in ("localhost", "localhost.localdomain") or host.casefold().endswith(".local")
            if parsed_url.scheme not in ("http", "https") or not host or private_host:
                return {"needs_clarification": True, "details_status": "invalid_url",
                        "clarification_question": "That does not look like a public job listing URL. Please share a public http/https job link or paste the description.",
                        "url": url}
            vendor = detect_ats_vendor(url)
            try:
                res = requests.get(url, timeout=15, headers={"User-Agent": "SpaceV job description reader (public listing)"})
                if res.status_code in (403, 429):
                    return {"needs_clarification": True, "details_status": "access_limited",
                            "clarification_question": f"The job page at {url} denied automated access (HTTP {res.status_code}). Please paste the job description or share another public listing link.",
                            "url": url, "ats_vendor": vendor}
                if res.status_code != 200:
                    return {"needs_clarification": True, "details_status": "http_error",
                            "clarification_question": f"I could not read the job page (HTTP {res.status_code}). Can you paste its description or provide another link?",
                            "url": url, "ats_vendor": vendor}
                soup = BeautifulSoup(res.text, "html.parser")
                visible_html_text = soup.get_text(" ", strip=True)
                js_shell_candidate = len(visible_html_text) < 180 and bool(
                    soup.find(id=re.compile(r"^(root|app|__next)$", re.I))
                    or soup.find("script", src=re.compile(r"\.js(?:\?|$)", re.I))
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
                    main_body = (soup.find("div", {"id": re.compile(r"job|content|description", re.I)})
                                 or soup.find("section", {"class": re.compile(r"job|content|description", re.I)})
                                 or soup.find("main") or soup.body)
                    raw_text = main_body.get_text(separator="\n", strip=True) if main_body else soup.get_text("\n", strip=True)
                details_source = "json_ld" if title or company else "page_text"
            except Exception as e:
                logger.warning(f"Live fetch failed for {url}: {e}")
                return {"needs_clarification": True, "details_status": "fetch_error",
                        "clarification_question": f"I couldn't retrieve the job details from {url} ({e.__class__.__name__}). Please paste the job description or give me another link.",
                        "url": url, "ats_vendor": vendor}
        else:
            raw_text = url_or_text.strip()

        if url and any(term in raw_text[:3000].casefold() for term in ("captcha", "verify you are human", "access denied", "robot check")):
            return {"needs_clarification": True, "details_status": "challenge",
                    "clarification_question": "The job site is asking for human verification or limiting access. Please open it yourself and paste the job description, or share another public link.",
                    "url": url, "ats_vendor": vendor}

        # Use plain Playwright only when a successful HTTP response is an empty JS shell.
        # No stealth plugins, CAPTCHA solving, proxying, or fingerprint changes are used.
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
                            return {"needs_clarification": True, "details_status": "access_limited",
                                    "clarification_question": f"The job page limited automated access (HTTP {response.status}). Please paste the job description or share another public listing link.",
                                    "url": url, "ats_vendor": vendor}
                        page_text = page.locator("body").inner_text(timeout=5000)
                        page_title = page.title()
                    finally:
                        browser.close()
                if any(term in (page_title + " " + page_text[:1200]).casefold()
                       for term in ("captcha", "verify you are human", "access denied", "robot check")):
                    return {"needs_clarification": True, "details_status": "challenge",
                            "clarification_question": "The job site is asking for a human verification or blocking access. Please open it yourself and paste the job description, or share a different public listing link.",
                            "url": url, "ats_vendor": vendor}
                if len(page_text.strip()) > len(raw_text.strip()):
                    raw_text = page_text
                    details_source = "playwright_visible_text"
                    if not title:
                        title = page_title
            except Exception as exc:
                logger.info("Plain Playwright job-page read unavailable: %s", exc.__class__.__name__)

        if len(raw_text.strip()) < 180:
            return {"needs_clarification": True, "details_status": "incomplete",
                    "clarification_question": "I found too little job-description text to identify the role and requirements reliably. Please paste the full description or share a more direct job link.",
                    "url": url, "ats_vendor": vendor, "raw_text": raw_text}
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
        candidate_data: Optional[Dict[str, Any]] = None
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
        auto_submit: bool = False
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

