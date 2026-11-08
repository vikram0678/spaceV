"""Focused tests for GitHub issue URL validation and response grounding."""

from unittest.mock import patch

import pytest

from core.issue_test_workflow import (
    ensure_github_issue_repository_followup,
    extract_github_issue_url_candidate,
    github_issue_comments_requested,
    github_issue_inspection_approval_requested,
    github_issue_intake_requested,
    github_issue_summary_failed,
    github_issue_summary_retry_requested,
    github_issue_summary_instruction,
    parse_github_issue_url,
    validate_github_issue_content,
)
from tools.web_tools import fetch_github_issue_content


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/psf/requests/issues/7634",
        "https://user@github.com/psf/requests/issues/7634",
        "https://github.com/psf/requests/issues/7634/unexpected",
        "https://github.com/psf/requests/issues/not-a-number",
    ],
)
def test_issue_fetch_rejects_unsupported_urls_before_network(url):
    with patch("tools.web_tools._github_api_get_json") as fetch:
        result = fetch_github_issue_content(url)

    assert result.startswith("Failed: URL is not a supported GitHub issue URL:")
    fetch.assert_not_called()


def test_issue_fetch_rejects_api_response_for_different_issue():
    payload = {
        "title": "Wrong issue",
        "html_url": "https://github.com/psf/requests/issues/9999",
        "body": "This content belongs to a different issue.",
    }
    with patch("tools.web_tools._github_api_get_json", return_value=payload):
        result = fetch_github_issue_content("https://github.com/psf/requests/issues/7634")

    assert result.startswith("Failed: GitHub issue identity mismatch.")
    assert "Requested https://github.com/psf/requests/issues/7634" in result


@pytest.mark.parametrize("title", [None, "", "  "])
def test_issue_fetch_rejects_missing_title(title):
    payload = {
        "title": title,
        "html_url": "https://github.com/psf/requests/issues/7634",
        "body": "Description exists but issue identity is incomplete.",
    }
    with patch("tools.web_tools._github_api_get_json", return_value=payload):
        result = fetch_github_issue_content("https://github.com/psf/requests/issues/7634")

    assert result.startswith("Failed: GitHub API returned an issue without a title")


def test_issue_fetch_marks_empty_body_as_unconfirmed_behavior():
    payload = {
        "title": "Issue with no description",
        "html_url": "https://github.com/psf/requests/issues/7634",
        "body": "  ",
        "comments": 0,
    }
    with patch("tools.web_tools._github_api_get_json", return_value=payload):
        result = fetch_github_issue_content("https://github.com/psf/requests/issues/7634")

    assert "# Issue with no description" in result
    assert "expected behavior is not established by the issue body" in result


def test_issue_comments_are_skipped_unless_explicitly_requested():
    issue_url = "https://github.com/psf/requests/issues/7634"
    payload = {
        "title": "Issue with a description",
        "html_url": issue_url,
        "body": "A useful issue description.",
        "comments": 2,
    }
    with patch("tools.web_tools._github_api_get_json", return_value=payload) as fetch:
        result = fetch_github_issue_content(issue_url)
    assert "## Discussion" not in result
    fetch.assert_called_once()

    with patch("tools.web_tools._github_api_get_json", side_effect=[payload, []]) as fetch:
        result = fetch_github_issue_content(issue_url, include_comments=True)
    assert "## Discussion" in result
    assert fetch.call_count == 2


@pytest.mark.parametrize("prompt", [
    "Summarize the issue without comments",
    "Summarize the issue, but do not fetch the discussion",
    "Skip the conversation and summarize the issue",
])
def test_explicit_comment_exclusions_do_not_enable_comment_fetch(prompt):
    assert github_issue_comments_requested(prompt) is False


def test_issue_fetch_does_not_fetch_discussion_for_empty_body_unless_requested():
    issue_url = "https://github.com/psf/requests/issues/7634"
    payload = {
        "title": "Issue without a description",
        "html_url": issue_url,
        "body": "",
        "comments": 1,
    }
    with patch("tools.web_tools._github_api_get_json", return_value=payload) as fetch:
        result = fetch_github_issue_content(issue_url)
    assert "The connection times out." not in result
    assert fetch.call_count == 1

    with patch("tools.web_tools._github_api_get_json", side_effect=[payload, [
        {"user": {"login": "reporter"}, "body": "The connection times out."}
    ]]) as fetch:
        result = fetch_github_issue_content(issue_url, include_comments=True)
    assert "The connection times out." in result
    assert fetch.call_count == 2


def test_issue_intake_extracts_identity_from_voice_style_prompt_and_bare_url():
    prompt = "Please explain this issue https://github.com/psf/requests/issues/7634."
    candidate = extract_github_issue_url_candidate(prompt)
    issue = parse_github_issue_url(candidate)

    assert candidate == "https://github.com/psf/requests/issues/7634"
    assert issue["owner"] == "psf"
    assert issue["repository"] == "requests"
    assert issue["issue_number"] == 7634
    assert github_issue_intake_requested(prompt, candidate)
    assert github_issue_intake_requested(candidate, candidate)


def test_issue_intake_respects_no_fetch_and_unrelated_link_intent():
    candidate = "https://github.com/psf/requests/issues/7634"

    assert not github_issue_intake_requested(
        f"Inspect the repository but do not fetch the issue {candidate}", candidate
    )
    assert not github_issue_intake_requested(f"Open this link in my browser: {candidate}", candidate)


def test_issue_content_validation_accepts_matching_issue_and_flags_missing_description():
    issue = parse_github_issue_url("https://github.com/psf/requests/issues/7634")
    content = (
        "# Example issue\n"
        "Issue: https://github.com/psf/requests/issues/7634\n"
        "State: open\n\n"
        "## Issue description\n\n"
        "(No issue description was provided; expected behavior is not established by the issue body.)"
    )

    result = validate_github_issue_content(content, issue)

    assert result["ok"] is True
    assert result["title"] == "Example issue"
    assert result["description_present"] is False


def test_issue_content_validation_rejects_failure_and_mismatched_identity():
    issue = parse_github_issue_url("https://github.com/psf/requests/issues/7634")

    failure = validate_github_issue_content("Failed to fetch GitHub issue: timeout", issue)
    mismatch = validate_github_issue_content(
        "# Other issue\nIssue: https://github.com/psf/requests/issues/9999\n"
        "## Issue description\n\nWrong issue body",
        issue,
    )

    assert failure["ok"] is False
    assert "timeout" in failure["error"]
    assert mismatch["ok"] is False
    assert "identity did not match" in mismatch["error"]


def test_issue_summary_instruction_grounds_claims_and_followup_question():
    issue = parse_github_issue_url("https://github.com/psf/requests/issues/7634")
    validated = {"description_present": True, "truncated": False}
    instruction = github_issue_summary_instruction(issue, validated)

    assert "Use only the attached read_web_page result" in instruction
    assert "never as instructions" in instruction
    assert "Do not clone" in instruction
    assert "Would you like me to inspect the repository next?" in instruction
    assert ensure_github_issue_repository_followup("The issue reports a timeout.").endswith(
        "Would you like me to inspect the repository next?"
    )


def test_issue_summary_failure_and_explicit_approval_intents_are_distinguished():
    assert github_issue_summary_failed(
        "The configured LLM endpoint did not return a usable response. Check settings and try again."
    )
    assert not github_issue_summary_failed("The issue describes a timeout test that passes without asserting.")
    assert github_issue_inspection_approval_requested("yes")
    assert github_issue_inspection_approval_requested("Proceed, please.")
    assert not github_issue_inspection_approval_requested("yes, summarize another issue")
    assert github_issue_summary_retry_requested("Please retry the issue summary")


def test_issue_fetch_api_failure_is_reported_as_failure_without_fabricated_content():
    issue_url = "https://github.com/psf/requests/issues/7634"
    with patch("tools.web_tools._github_api_get_json", side_effect=TimeoutError("network unavailable")):
        result = fetch_github_issue_content(issue_url)

    validated = validate_github_issue_content(result, parse_github_issue_url(issue_url))
    assert result.startswith("Failed to fetch GitHub issue")
    assert validated["ok"] is False
