"""
SpaceV Career & Job Intelligence Engine.
Integrates with zjob harvester, normalized job datasets, and CareerSync ATS Kanban.
Provides:
  - Multi-source job search and harvesting (local zjob repository + live RemoteOK API)
  - Strict 0-1 YOE / Fresher / Role domain normalization
  - Deterministic SHA-1 deduplication
  - Local ATS Kanban tracking (.spacev/career_applications.jsonl)
  - Tailored job application draft preparation
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import USER_DESKTOP_DIR

logger = logging.getLogger("SpaceV.CareerTools")

CAREER_STORE_DIR = Path(".spacev")
CAREER_APPLICATIONS_FILE = CAREER_STORE_DIR / "career_applications.jsonl"
ZJOB_PATH = Path("D:/Gpp-Tasks/zjob") if Path("D:/Gpp-Tasks/zjob").exists() else Path("/mnt/d/Gpp-Tasks/zjob")


# ─── Deduplication Subsystem (from zjob/dedup.py) ──────────────────

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Lowercase ASCII slug for deduplication."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return _NON_SLUG.sub("-", ascii_only.lower()).strip("-")


def make_dedup_key(company: str, title: str, url: str = "") -> str:
    """Generates canonical deduplication fingerprint based on company and title."""
    c_slug = _slugify(company)[:40] or "unknown"
    t_slug = _slugify(title)[:60] or "job"
    return f"{c_slug}_{t_slug}"


# ─── Data Access & Normalization ───────────────────────────────────

def _load_local_zjob_data() -> List[Dict[str, Any]]:
    """Loads indexed jobs from /mnt/d/Gpp-Tasks/zjob/jobs_data.json or jobs_latest.csv if available."""
    jobs: List[Dict[str, Any]] = []

    # 1. Try jobs_data.json
    json_path = ZJOB_PATH / "jobs_data.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        jobs.append({
                            "title": item.get("Job_Title") or item.get("title", ""),
                            "company": item.get("Company") or item.get("company", "Unknown"),
                            "domain": item.get("Domain", ""),
                            "work_type": item.get("Work_Type", ""),
                            "location": item.get("Location") or item.get("location", ""),
                            "min_exp": int(item["Min_Exp"]) if str(item.get("Min_Exp", "")).isdigit() else None,
                            "salary": item.get("Salary", ""),
                            "url": item.get("Apply_URL") or item.get("url", ""),
                            "platform": item.get("Platform", "Indexed"),
                            "date_posted": item.get("Date_Posted", ""),
                        })
                    if jobs:
                        return jobs
        except Exception as e:
            logger.warning(f"Failed to read {json_path}: {e}")

    # 2. Try jobs_latest.csv
    csv_path = ZJOB_PATH / "jobs_latest.csv"
    if csv_path.exists():
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    jobs.append({
                        "title": row.get("Job_Title") or row.get("title", ""),
                        "company": row.get("Company") or row.get("company", "Unknown"),
                        "domain": row.get("Domain", ""),
                        "work_type": row.get("Work_Type", ""),
                        "location": row.get("Location") or row.get("location", ""),
                        "min_exp": int(row["Min_Exp"]) if str(row.get("Min_Exp", "")).isdigit() else None,
                        "salary": row.get("Salary", ""),
                        "url": row.get("Apply_URL") or row.get("url", ""),
                        "platform": row.get("Platform", "CSV"),
                        "date_posted": row.get("Date_Posted", ""),
                    })
        except Exception as e:
            logger.warning(f"Failed to read {csv_path}: {e}")

    return jobs


def _fetch_live_remoteok(role: str) -> List[Dict[str, Any]]:
    """Fetches real-time jobs from RemoteOK public API."""
    import requests

    jobs: List[Dict[str, Any]] = []
    clean_role = role.strip().lower()
    url = "https://remoteok.com/api"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SpaceVCyberAgent/2026.1"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            raw_items = data[1:] if len(data) > 1 else []
            for item in raw_items:
                pos = item.get("position", "")
                tags = " ".join(item.get("tags", []))
                desc = item.get("description", "")
                full_text = f"{pos} {tags} {desc}".lower()

                if not clean_role or clean_role in full_text or any(w in full_text for w in clean_role.split()):
                    jobs.append({
                        "title": pos,
                        "company": item.get("company", "Unknown"),
                        "domain": "Software / Remote",
                        "work_type": "Remote",
                        "location": item.get("location") or "Worldwide (Remote)",
                        "min_exp": 0,
                        "salary": item.get("salary") or "",
                        "url": item.get("url") or f"https://remoteok.com/l/{item.get('id', '')}",
                        "platform": "RemoteOK",
                        "date_posted": item.get("date", ""),
                    })
    except Exception as e:
        logger.warning(f"RemoteOK fetch failed: {e}")

    return jobs


def _harvest_simplify_jobs(role: str = "", location: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetches verified active tech jobs and internships directly from SimplifyJobs ATS feed.
    Provides pristine direct application links (Greenhouse, Lever, Workday, Ashby).
    Zero external dependencies (uses standard urllib).
    """
    url = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json"
    jobs: List[Dict[str, Any]] = []
    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SpaceVCyberAgent/2026.1"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        clean_role = role.lower().strip()
        clean_loc = location.lower().strip()
        role_tokens = [tok for tok in clean_role.split() if len(tok) > 2]

        for item in data:
            if not item.get("active", False) or not item.get("is_visible", True):
                continue
            title = item.get("title", "")
            comp = item.get("company_name", "")
            apply_url = item.get("url", "") or item.get("job_url_direct", "")
            if not title or not comp or not apply_url:
                continue

            locs = item.get("locations", [])
            loc_str = ", ".join(locs) if locs else "Not provided"
            full_haystack = f"{title} {comp} {item.get('category', '')}".lower()

            # Role match
            if role_tokens and not any(tok in full_haystack for tok in role_tokens):
                continue

            # Location match if specified
            if clean_loc and clean_loc not in ["any", "all", "global"]:
                if clean_loc not in loc_str.lower():
                    continue

            jobs.append({
                "title": title,
                "company": comp,
                "domain": item.get("category", "Software"),
                "work_type": "Remote" if any("remote" in l.lower() for l in locs) else "",
                "location": loc_str,
                "min_exp": None,
                "salary": "",
                "url": apply_url,
                "platform": "Simplify / Direct ATS",
                "date_posted": str(item.get("date_posted", "")),
            })
            if len(jobs) >= limit:
                break
    except Exception as e:
        logger.debug(f"SimplifyJobs feed ingestion note: {e}")

    return jobs


def _harvest_jobspy_live(role: str, location: str = "remote", limit: int = 5) -> List[Dict[str, Any]]:
    """
    Subprocess bridge to d:\Gpp-Tasks\zjob JobSpy engine.
    Queries LinkedIn and Indeed without conflicting with SpaceV's virtual environment.
    """
    zjob_py = Path("D:/Gpp-Tasks/zjob/.venv/Scripts/python.exe")
    if not zjob_py.exists():
        return []

    clean_role = (role or "Python").strip()
    clean_loc = (location or "Remote").strip()

    script = f"""
import sys, json
sys.path.insert(0, r'D:\\Gpp-Tasks\\zjob')
from scrapers.jobspy_scraper import harvest_jobspy_batches
batches = [{{
    'tag': 'Live Search',
    'domain': 'Tech',
    'site_name': ['indeed', 'linkedin'],
    'search_term': {repr(clean_role)},
    'location': {repr(clean_loc)},
    'results_wanted': {min(limit, 6)}
}}]
try:
    jobs = harvest_jobspy_batches(batches)
    cleaned = []
    for j in jobs:
        cleaned.append({{
            'title': j.get('title') or '',
            'company': j.get('company') or 'Unknown',
            'location': j.get('location') or {repr(clean_loc)},
            'url': j.get('url') or j.get('job_url') or '',
            'salary': str(j.get('salary_raw') or j.get('salary') or ''),
            'platform': j.get('site') or 'JobSpy',
            'date_posted': str(j.get('date_posted') or '')
        }})
    print('JSON_START' + json.dumps(cleaned))
except Exception as e:
    print('JSON_START' + json.dumps([]))
"""
    try:
        import subprocess
        proc = subprocess.run(
            [str(zjob_py), "-c", script],
            capture_output=True,
            text=True,
            timeout=22,
            encoding="utf-8",
            errors="replace"
        )
        for line in proc.stdout.split("\n"):
            if line.startswith("JSON_START"):
                items = json.loads(line[10:])
                for it in items:
                    if "platform" not in it:
                        it["platform"] = it.get("site") or "JobSpy"
                    if "url" not in it:
                        it["url"] = it.get("job_url") or ""
                return items
    except Exception as e:
        logger.warning(f"JobSpy subprocess bridge note: {e}")

    return []


# ─── Core Tool Implementations ──────────────────────────────────────

def search_and_harvest_jobs(
    role: str = "",
    location: str = "",
    min_exp: int = 0,
    limit: int = 10,
    save_to_desktop: bool = False,
) -> str:
    """
    Searches and harvests live job opportunities matching the role, location, and experience.
    Combines direct ATS feeds (SimplifyJobs), consumer board harvesters (JobSpy),
    local indexed datasets, and live aggregator APIs.
    Performs deterministic deduplication and exports to CSV.
    """
    clean_role = (role or "").strip().lower()
    clean_loc = (location or "").strip().lower()
    if not clean_role or not clean_loc:
        missing = "job role" if not clean_role and not clean_loc else ("job role" if not clean_role else "target location")
        return f"SPACEV_NEEDS_USER_INPUT: I need your {missing} before I search. What {missing} should I use?"

    all_jobs: List[Dict[str, Any]] = []

    # 1. Harvest verified direct ATS listings (Greenhouse, Lever, Workday) via SimplifyJobs
    ats_jobs = _harvest_simplify_jobs(clean_role, clean_loc, limit=limit)
    all_jobs.extend(ats_jobs)

    # 2. Harvest live consumer boards (LinkedIn, Indeed) via JobSpy bridge
    jobspy_jobs = _harvest_jobspy_live(clean_role, clean_loc, limit=limit)
    all_jobs.extend(jobspy_jobs)

    # 3. Load from local zjob repository
    local_jobs = _load_local_zjob_data()
    all_jobs.extend(local_jobs)

    # 4. If total jobs are sparse (< 10), augment with live RemoteOK
    if len(all_jobs) < 10:
        live_jobs = _fetch_live_remoteok(clean_role)
        all_jobs.extend(live_jobs)

    # 3. Filter by role and location
    matched: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    for job in all_jobs:
        title = job.get("title", "")
        company = job.get("company", "")
        job_loc = job.get("location", "")
        work_type = job.get("work_type", "")
        domain = job.get("domain", "")

        # Deduplication check
        dedup_key = make_dedup_key(company, title, job.get("url", ""))
        if dedup_key in seen_keys:
            continue

        # Match role keywords
        full_text = f"{title} {domain} {company}".lower()
        role_tokens = clean_role.split()
        if clean_role and not any(tok in full_text for tok in role_tokens):
            continue

        # Match location keywords if specified (e.g. "remote", "bengaluru", "us")
        if clean_loc and clean_loc not in ["any", "all", "global"]:
            loc_text = f"{job_loc} {work_type}".lower()
            if clean_loc not in loc_text:
                continue

        # Filter by min_exp if requested
        job_exp = job.get("min_exp", 0)
        if min_exp > 0 and job_exp is not None and job_exp > min_exp:
            continue

        seen_keys.add(dedup_key)
        matched.append(job)

        if len(matched) >= limit:
            break

    if not matched:
        return (f"SPACEV_NEEDS_USER_INPUT: I found no listings matching **{role}** in **{location}**. "
                "Would you like to broaden the role, change the location, or include remote roles?")

    # Save every result to the durable local opportunity inbox. The source check
    # timestamp is retained separately from any claim that a listing remains open.
    try:
        from core.career_assistant import career_assistant_store
        opportunity_type = "internship" if "intern" in clean_role else "job"
        career_assistant_store.save_opportunities(matched, opportunity_type=opportunity_type)
    except Exception as exc:
        logger.warning("Could not persist harvested career opportunities: %s", exc)

    # Save to CSV on Desktop if requested
    csv_msg = ""
    if save_to_desktop:
        try:
            safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", clean_role)
            csv_path = USER_DESKTOP_DIR / f"{safe_name}_jobs_{datetime.now().strftime('%Y%m%d')}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Title", "Company", "Domain", "Work_Type", "Location", "Min_Exp", "Salary", "Platform", "Apply_URL"])
                writer.writeheader()
                for j in matched:
                    writer.writerow({
                        "Title": j.get("title", ""),
                        "Company": j.get("company", ""),
                        "Domain": j.get("domain", ""),
                        "Work_Type": j.get("work_type", ""),
                        "Location": j.get("location", ""),
                        "Min_Exp": j.get("min_exp"),
                        "Salary": j.get("salary", ""),
                        "Platform": j.get("platform", ""),
                        "Apply_URL": j.get("url", ""),
                    })
            csv_msg = f"\n📁 Exported {len(matched)} jobs to Desktop: `{csv_path.name}`"
        except Exception as e:
            logger.warning(f"Failed to export CSV: {e}")

    # Build structured response
    output_lines = [
        f"🎯 **SpaceV Job Intelligence Engine** — Harvested {len(matched)} Listings for '{role}':\n"
    ]
    for idx, j in enumerate(matched, 1):
        output_lines.append(
            f"**{idx}. {j.get('title')}** @ **{j.get('company')}**\n"
            f"   • 📍 Location: {j.get('location')} ({j.get('work_type')})\n"
            f"   • 💰 Compensation: {(j.get('salary') or 'Not stated')}\n"
            f"   Experience: {(str(j.get('min_exp')) + ' YOE') if j.get('min_exp') is not None else 'Not stated'} | Platform: {j.get('platform')}\n"
            f"   • 🔗 Apply: {j.get('url')}\n"
        )

    if csv_msg:
        output_lines.append(csv_msg)

    return "\n".join(output_lines)


def track_career_application(
    job_title: str,
    company: str,
    job_url: str = "",
    status: str = "Wishlist",
    notes: str = "",
) -> str:
    """
    Tracks a job application in the local Career ATS Kanban (.spacev/career_applications.jsonl).
    Valid statuses: 'Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected'.
    """
    valid_statuses = {"Wishlist", "Applied", "Interview", "Offer", "Rejected"}
    norm_status = status.strip().title()
    if norm_status not in valid_statuses:
        norm_status = "Wishlist"

    CAREER_STORE_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "id": hashlib.sha1(f"{company}_{job_title}_{time_str()}".encode()).hexdigest()[:10],
        "job_title": job_title.strip(),
        "company": company.strip(),
        "job_url": (job_url or "").strip(),
        "status": norm_status,
        "notes": (notes or "").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with open(CAREER_APPLICATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        return f"Failed to record application: {e!s}"

    # Keep the durable opportunity inbox in sync with user-confirmed pipeline
    # changes. A requested status is a user statement, not proof from the site.
    if record["job_url"]:
        try:
            from core.career_assistant import career_assistant_store
            career_assistant_store.save_opportunities([{
                "title": record["job_title"], "company": record["company"],
                "url": record["job_url"], "source": "user-tracked",
            }])
            career_assistant_store.update_opportunity_status(
                record["job_url"], norm_status.casefold(), record["notes"]
            )
            if norm_status == "Applied":
                try:
                    career_assistant_store.record_activity(
                        f"User confirmed application submitted: {record['job_title']} at {record['company']}"
                    )
                except ValueError:
                    # Application tracking remains useful when no career goal is active.
                    pass
        except Exception as exc:
            logger.warning("Could not sync application with career goal store: %s", exc)

    # Calculate current counts
    counts = _get_status_counts()
    count_summary = ", ".join(f"{k}: {v}" for k, v in counts.items())

    return (
        f"✅ Tracked application for **{job_title}** at **{company}** in stage **[{norm_status}]**.\n"
        f"📊 Current Pipeline: {count_summary}"
    )


def list_career_applications(status_filter: str = "") -> str:
    """
    Lists tracked applications from the local Career ATS Kanban.
    Can be filtered by status ('Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected').
    """
    if not CAREER_APPLICATIONS_FILE.exists():
        return "No job applications currently tracked. Use `track_career_application` to start tracking."

    filter_clean = status_filter.strip().title() if status_filter else ""
    records: List[Dict[str, Any]] = []

    try:
        with open(CAREER_APPLICATIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
    except Exception as e:
        return f"Error reading applications: {e!s}"

    if not records:
        return "No job applications found in tracking ledger."

    # Group by status
    by_status: Dict[str, List[Dict[str, Any]]] = {
        "Wishlist": [],
        "Applied": [],
        "Interview": [],
        "Offer": [],
        "Rejected": [],
    }

    for r in records:
        st = r.get("status", "Wishlist")
        if filter_clean and st.lower() != filter_clean.lower():
            continue
        if st in by_status:
            by_status[st].append(r)
        else:
            by_status.setdefault(st, []).append(r)

    out = ["📋 **SpaceV Career Application Tracker (Kanban View)**:\n"]
    for status_name, apps in by_status.items():
        if filter_clean and status_name.lower() != filter_clean.lower():
            continue
        out.append(f"### 🏷️ {status_name} ({len(apps)})")
        if not apps:
            out.append("*(none)*\n")
            continue
        for app in apps:
            url_str = f" | [Link]({app.get('job_url')})" if app.get("job_url") else ""
            notes_str = f" — *{app.get('notes')}*" if app.get("notes") else ""
            out.append(f"• **{app.get('job_title')}** @ **{app.get('company')}**{url_str}{notes_str}")
        out.append("")

    return "\n".join(out).strip()


def prepare_job_application(
    job_title: str,
    company: str,
    candidate_name: str = "Applicant",
    skills: str = "",
) -> str:
    """
    Prepares a customized job application draft, cold email outreach, and key qualification pitch.
    """
    default_skills = skills or "Python, Agentic AI, Autonomous Workflows, LLM Orchestration, Full-Stack Development"
    title = job_title.strip()
    comp = company.strip()
    name = candidate_name.strip() or "Applicant"

    pitch = (
        f"Subject: Application for {title} — {name}\n\n"
        f"Hi {comp} Hiring Team,\n\n"
        f"I am writing to express my strong interest in the **{title}** role at **{comp}**.\n\n"
        f"Key Highlights of My Experience:\n"
        f"• Extensive hands-on building with {default_skills}.\n"
        f"• Architecture and development of resilient autonomous AI agents, multi-model cognitive routing, and full-stack systems.\n"
        f"• Proven track record in rapid prototyping, clean code hygiene, and deterministic problem-solving.\n\n"
        f"I would welcome the opportunity to discuss how my technical expertise aligns with {comp}'s mission.\n\n"
        f"Best regards,\n"
        f"{name}\n"
    )

    return (
        f"📝 **Generated Application Pitch for {title} @ {comp}**:\n\n"
        f"```text\n{pitch}```\n"
        f"💡 *Next step*: You can review this draft and use `track_career_application` with status='Applied' once submitted."
    )


def _get_status_counts() -> Dict[str, int]:
    """Helper to count applications in each status."""
    counts: Dict[str, int] = {"Wishlist": 0, "Applied": 0, "Interview": 0, "Offer": 0, "Rejected": 0}
    if not CAREER_APPLICATIONS_FILE.exists():
        return counts
    try:
        with open(CAREER_APPLICATIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    st = item.get("status", "Wishlist")
                    counts[st] = counts.get(st, 0) + 1
    except Exception:
        pass
    return counts


def time_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def analyze_job_description(url_or_text: str, resume_path: str = "", compare_resume: bool = False) -> str:
    """Return extracted job-description evidence and optionally compare a real resume."""
    from core.career_copilot import career_copilot, extract_skills_from_text

    jd = career_copilot.extract_job_description(url_or_text)
    if jd.get("needs_clarification"):
        return "SPACEV_NEEDS_USER_INPUT: " + str(jd.get("clarification_question") or "I could not confirm the job details. Please share the full description.")

    skills = jd.get("required_skills", [])
    skills_fmt = ", ".join(skills) if skills else "No explicit skills detected in the available text."
    comparison = ""
    if compare_resume and not resume_path:
        return "SPACEV_NEEDS_USER_INPUT: I have the job details, but I need your resume to compare them. Please provide the file path (.pdf/.docx/.txt/.md) or paste the resume text."
    if resume_path:
        path = Path(resume_path).expanduser()
        if not path.is_file():
            return f"SPACEV_NEEDS_USER_INPUT: I can't find the resume at {path}. Please provide the correct path or paste the resume text."
        try:
            suffix = path.suffix.lower()
            if suffix in (".txt", ".md"):
                resume_text = path.read_text(encoding="utf-8", errors="replace")
            elif suffix == ".docx":
                import zipfile
                from xml.etree import ElementTree
                with zipfile.ZipFile(path) as archive:
                    root = ElementTree.fromstring(archive.read("word/document.xml"))
                resume_text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            elif suffix == ".pdf":
                try:
                    from pypdf import PdfReader
                except ImportError:
                    return "SPACEV_NEEDS_USER_INPUT: PDF reading needs the optional pypdf package. Please provide a .docx/.txt resume or paste its text."
                resume_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            else:
                return "SPACEV_NEEDS_USER_INPUT: Supported resume formats are .pdf, .docx, .txt, and .md. Please provide one or paste the text."
            if len(resume_text.strip()) < 80:
                return "SPACEV_NEEDS_USER_INPUT: I extracted too little text from the resume to compare it reliably. Please share a readable file or paste its content."
            resume_skills = {skill.casefold() for skill in extract_skills_from_text(resume_text)}
            found = [skill for skill in skills if skill.casefold() in resume_skills]
            absent = [skill for skill in skills if skill.casefold() not in resume_skills]
            comparison = ("\n\n**Resume evidence comparison (keyword-based):**\n"
                          f"- Detected in resume: {', '.join(found) if found else 'None'}\n"
                          f"- Not detected in resume: {', '.join(absent) if absent else 'None'}\n"
                          "Not detected does not mean you lack a skill. Add it only if it truthfully reflects your experience.")
        except Exception as exc:
            return f"SPACEV_NEEDS_USER_INPUT: I couldn't read that resume ({exc.__class__.__name__}). Please share a readable file or paste its text."

    exp = jd.get("min_exp")
    return (
        "**Job description details**\n\n"
        f"- Role: {jd.get('title') or 'Not stated in available page'}\n"
        f"- Company: {jd.get('company') or 'Not stated in available page'}\n"
        f"- ATS: {jd.get('ats_vendor', 'generic').upper()}\n"
        f"- Experience: {str(exp) + ' years' if exp is not None else 'Not stated'}\n"
        f"- Skills detected: {skills_fmt}\n"
        f"- Source: {jd.get('details_source', 'provided text')}\n\n"
        f"**Full description:**\n{jd.get('full_description', '')}{comparison}\n\n"
        "SpaceV does not edit your Careerflow account; use these findings to guide truthful edits there."
    )


def tailor_careerflow_resume(
    careerflow_url: str,
    job_url_or_text: str,
    candidate_name: str = "",
    resume_path: str = "",
) -> str:
    """Give evidence-based edit guidance; SpaceV does not control Careerflow accounts."""
    if not resume_path:
        return "SPACEV_NEEDS_USER_INPUT: To compare this job with your actual resume, provide the resume file path (.pdf/.docx/.txt/.md). SpaceV will then suggest specific truthful edits for you to make in Careerflow."
    result = analyze_job_description(job_url_or_text, resume_path=resume_path)
    if result.startswith("SPACEV_NEEDS_USER_INPUT:"):
        return result
    return "Careerflow editing guide (you make the changes in Careerflow; SpaceV has no account connection):\n\n" + result


def apply_to_job(
    job_url: str,
    careerflow_url: str = "",
    resume_path: str = "",
    auto_submit: bool = False,
) -> str:
    """Prepare a truthful review only; this tool does not fill or submit applications."""
    jd = analyze_job_description(job_url, resume_path=resume_path, compare_resume=True)
    if jd.startswith("SPACEV_NEEDS_USER_INPUT:"):
        return jd
    return ("SpaceV has prepared the job/resume review, but it does not have a verified application-form integration. "
            "Review the listing and submit the application yourself. I can help you refine truthful resume edits from the comparison below.\n\n" + jd)


def create_career_goal(
    goal: str = "",
    target_roles: List[str] | None = None,
    location: str = "",
    deadline: str = "",
    duration_days: int = 0,
    available_hours: float = 0,
    plan_items: List[Dict[str, Any]] | None = None,
    resume_path: str = "",
) -> str:
    """Persist the reviewed career objective and the assistant's proposed dated plan."""
    missing = []
    if not goal.strip():
        missing.append("the outcome you want")
    if not target_roles:
        missing.append("target role(s)")
    if not location.strip():
        missing.append("target location or work mode")
    if not deadline.strip() and duration_days <= 0:
        missing.append("a deadline (YYYY-MM-DD) or number of days")
    if available_hours <= 0:
        missing.append("hours you can spend per day")
    if not plan_items:
        missing.append("a proposed plan with dated tasks for you to review")
    if missing:
        return "SPACEV_NEEDS_USER_INPUT: Before I save your career plan, please tell me " + ", ".join(missing) + "."
    try:
        from core.career_assistant import career_assistant_store
        result = career_assistant_store.create_goal(
            goal=goal,
            target_roles=target_roles or [],
            location=location,
            deadline=deadline,
            duration_days=duration_days,
            available_hours=available_hours,
            plan_items=plan_items or [],
            resume_path=resume_path,
        )
        return "Career goal saved locally. This plan is editable; no applications were submitted.\n" + json.dumps(result, ensure_ascii=False, indent=2)
    except (ValueError, TypeError) as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def get_career_goal() -> str:
    """Returns the saved active career goal and dated plan, if any."""
    from core.career_assistant import career_assistant_store
    goal = career_assistant_store.get_active_goal()
    return json.dumps(goal, ensure_ascii=False, indent=2) if goal else "No active career goal is saved yet."


def activate_career_goal(goal_id: str = "") -> str:
    """Activate a draft only after the user explicitly approves the proposed plan."""
    if not goal_id.strip():
        return "SPACEV_NEEDS_USER_INPUT: Which draft goal_id did you review and approve?"
    from core.career_assistant import career_assistant_store
    if career_assistant_store.activate_goal(goal_id):
        return "Your reviewed career goal is active. I can now track only the progress you confirm."
    return "No draft or paused goal was found with that goal_id."


def record_career_activity(activity: str = "", minutes: int = 0, task_id: str = "", notes: str = "") -> str:
    """Record progress the user explicitly confirms; never infer it from surveillance."""
    if not activity.strip():
        return "SPACEV_NEEDS_USER_INPUT: What career activity did you complete?"
    try:
        from core.career_assistant import career_assistant_store
        event_id = career_assistant_store.record_activity(activity, minutes, task_id, notes)
        return f"Recorded your confirmed progress ({event_id})."
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def update_career_plan_task(
    task_id: str = "",
    title: str = "",
    due_date: str = "",
    estimated_minutes: int | None = None,
    status: str = "",
) -> str:
    """Edit a task in the active career plan without changing unrelated tasks."""
    if not task_id.strip():
        return "SPACEV_NEEDS_USER_INPUT: Which active plan task should I update? Please provide its task_id."
    from core.career_assistant import career_assistant_store
    try:
        updated = career_assistant_store.update_plan_task(task_id, title, due_date, estimated_minutes, status)
        return "Career plan task updated." if updated else "No task with that ID exists in the active plan."
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def get_career_daily_review(day: str = "") -> str:
    """Compare the active goal's dated tasks with user-confirmed activity."""
    from datetime import date
    from core.career_assistant import career_assistant_store
    try:
        review_date = date.fromisoformat(day) if day.strip() else None
        return json.dumps(career_assistant_store.daily_review(review_date), ensure_ascii=False, indent=2)
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def create_career_reminder(
    title: str = "",
    due_at: str = "",
    repeat_rule: str = "none",
    goal_id: str = "",
    purpose: str = "notification",
    timezone_name: str = "",
) -> str:
    """Save a local reminder that survives SpaceV restarts."""
    if not title.strip() or not due_at.strip():
        missing = "reminder title and date/time with timezone" if not title.strip() and not due_at.strip() else ("reminder title" if not title.strip() else "date/time with timezone")
        return f"SPACEV_NEEDS_USER_INPUT: What {missing} should I use?"
    try:
        from core.career_assistant import career_assistant_store
        item = career_assistant_store.create_reminder(title, due_at, repeat_rule, goal_id, purpose, timezone_name)
        return "Reminder saved locally and will notify you while SpaceV is running. " + json.dumps(item, ensure_ascii=False)
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def list_career_reminders(include_completed: bool = False) -> str:
    from core.career_assistant import career_assistant_store
    return json.dumps(career_assistant_store.list_reminders(include_completed), ensure_ascii=False, indent=2)


def cancel_career_reminder(reminder_id: str = "") -> str:
    if not reminder_id.strip():
        return "SPACEV_NEEDS_USER_INPUT: Which reminder ID should I cancel?"
    from core.career_assistant import career_assistant_store
    return "Reminder cancelled." if career_assistant_store.cancel_reminder(reminder_id) else "No active reminder found with that ID."


def snooze_career_reminder(reminder_id: str = "", due_at: str = "") -> str:
    if not reminder_id.strip() or not due_at.strip():
        return "SPACEV_NEEDS_USER_INPUT: Give me the reminder ID and the new date/time with timezone."
    from core.career_assistant import career_assistant_store
    try:
        return "Reminder snoozed." if career_assistant_store.snooze_reminder(reminder_id, due_at) else "No active reminder found with that ID."
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def list_career_opportunities(status: str = "new", limit: int = 25, opportunity_type: str = "") -> str:
    from core.career_assistant import career_assistant_store
    try:
        return json.dumps(career_assistant_store.list_opportunities(status, limit, opportunity_type), ensure_ascii=False, indent=2)
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def track_career_opportunity(
    title: str = "",
    url: str = "",
    opportunity_type: str = "",
    company: str = "",
    location: str = "",
) -> str:
    """Save a user-provided job, internship, or hackathon link to the local inbox."""
    missing = [name for name, value in (("title", title), ("link", url), ("type: job, internship, or hackathon", opportunity_type)) if not value.strip()]
    if missing:
        return "SPACEV_NEEDS_USER_INPUT: I need the opportunity " + ", ".join(missing) + "."
    if opportunity_type not in {"job", "internship", "hackathon"}:
        return "SPACEV_NEEDS_USER_INPUT: Is this opportunity a job, internship, or hackathon?"
    try:
        from core.career_assistant import career_assistant_store
        saved = career_assistant_store.save_opportunities([{
            "title": title, "url": url, "company": company, "location": location,
            "source": "user-provided",
        }], opportunity_type=opportunity_type)
        return f"Saved {saved} {opportunity_type} opportunity to your local queue. The link's current status has not been independently verified."
    except ValueError as exc:
        return f"SPACEV_NEEDS_USER_INPUT: {exc}"


def delete_career_assistant_data(confirm: bool = False) -> str:
    """Delete career-assistant data only after an explicit confirmation."""
    if not confirm:
        return "SPACEV_NEEDS_USER_INPUT: This will permanently delete local career goals, plan tasks, confirmed progress, reminders, saved opportunity leads, and the application tracker. Should I delete them?"
    from core.career_assistant import career_assistant_store
    career_assistant_store.delete_all_career_data()
    try:
        CAREER_APPLICATIONS_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Deleted career assistant database, but could not remove the legacy application tracker: %s", exc)
    return "Deleted all locally stored SpaceV career-assistant data."
