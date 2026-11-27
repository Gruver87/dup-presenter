"""LinkedIn copy for a publish pack: a post and a first comment, each checked against a character limit.

Limits:
- Post body: 3,000 characters (LinkedIn's post limit).
- Comment: 1,250 characters. An earlier comment in this project was refused at about 2,100, so this limit
  is treated as enforced.
- The "see more" cut-off (about 200 characters) is a readability guideline, not a documented limit.

The copy is English, because the LinkedIn audience and the English deck variant are the target. Every fact
in it comes from the resolved deck or from a QA report that passed for the same file. Nothing is invented.
"""

from __future__ import annotations

from typing import Any

POST_MAX_CHARS = 3000
COMMENT_MAX_CHARS = 1250
HOOK_TARGET_CHARS = 200
DISCLAIMER = "R&D software. Not financial advice."


def _normalise_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    return url if url.startswith("http") else f"https://{url}"


def build_linkedin_copy(
    resolved: dict[str, Any],
    *,
    chapters: list[dict[str, Any]],
    qa_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``{"post", "comment", "post_chars", "comment_chars", "errors"}``.

    ``errors`` is empty only when both texts fit their limits. ``qa_report`` adds a line about the file only
    when that report passed (``ok`` and no hard failures), so an unchecked file is never described as checked.
    """
    slides = resolved.get("slides") or []
    hero = slides[0] if slides else {}
    outro = slides[-1] if slides else {}
    # No fallback to brand or slug: a slug as the LinkedIn headline is not the deck's message, so it is an error.
    headline = " ".join(str(hero.get("title") or "").split())
    subtitle = " ".join(str(hero.get("subtitle") or "").split())
    url = _normalise_url(str(outro.get("url") or ""))

    hook = f"{headline}: {subtitle}" if subtitle else headline
    post_parts = [
        hook,
        "",
        "Produced end to end with DUP Presenter, our open-source video pipeline: deck to narration, captions,"
        " render, loudness normalisation and a media QA gate.",
    ]
    if url:
        post_parts += ["", f"Repository: {url}"]
    post_parts += ["", DISCLAIMER]
    post = "\n".join(post_parts)

    chapter_line = " | ".join(f"{c['time']} {c['title']}" for c in chapters)
    comment_parts = [f"Chapters: {chapter_line}" if chapter_line else ""]
    if qa_report and qa_report.get("ok") and int(qa_report.get("hard_fails") or 0) == 0:
        audio = qa_report.get("audio") or {}
        comment_parts.append(
            "How the MP4 was checked: "
            f"{qa_report.get('width')}x{qa_report.get('height')}, "
            f"{qa_report.get('duration_sec')} s, "
            f"{audio.get('integrated_lufs')} LUFS, "
            f"true peak {audio.get('true_peak_dbtp')} dBTP. Media QA was run on this exact file."
        )
    comment = "\n\n".join(p for p in comment_parts if p)

    errors: list[str] = []
    if not headline:
        errors.append("post: deck has no headline (first slide title)")
    if len(post) > POST_MAX_CHARS:
        errors.append(f"post is {len(post)} characters, limit {POST_MAX_CHARS}")
    if len(comment) > COMMENT_MAX_CHARS:
        errors.append(f"comment is {len(comment)} characters, limit {COMMENT_MAX_CHARS}")
    return {
        "post": post,
        "comment": comment,
        "post_chars": len(post),
        "comment_chars": len(comment),
        "errors": errors,
    }


def render_linkedin_md(slug: str, copy: dict[str, Any]) -> str:
    """Markdown for out/<slug>_linkedin.md with the measured lengths and an explicit OK / OVER LIMIT status."""

    def status(n: int, limit: int) -> str:
        return "OK" if n <= limit else "OVER LIMIT"

    return "\n".join([
        f"# LinkedIn — `{slug}`",
        "",
        f"- Post: {copy['post_chars']} / {POST_MAX_CHARS} characters, {status(copy['post_chars'], POST_MAX_CHARS)}",
        f"- First comment: {copy['comment_chars']} / {COMMENT_MAX_CHARS} characters, "
        f"{status(copy['comment_chars'], COMMENT_MAX_CHARS)}",
        "",
        "## Post",
        "",
        copy["post"],
        "",
        "## First comment",
        "",
        copy["comment"],
        "",
    ])
