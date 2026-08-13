"""Short links, with a fallback.

Two providers, both keyless, tried in order:

  ulvis.net  primary.   Honours custom aliases, reports collisions clearly, and
                        did not rate-limit across repeated runs.
  is.gd      fallback.  The obvious first choice on paper, but it answers
                        "Error, database insert failed" to perfectly valid
                        requests once you have made a few in quick succession,
                        so it cannot be relied on alone.

If both refuse, the caller keeps the host's own URL -- longer, but it works.

Aliases are restricted to letters and digits because ulvis silently strips
anything else: asking for "my-file" yields "myfile", and a link that is not the
one you typed is worse than being told to retype it.
"""

from __future__ import annotations

import re

import requests

ULVIS_URL = "https://ulvis.net/api.php"
IS_GD_URL = "https://is.gd/create.php"
TIMEOUT = (10, 30)

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9]{5,30}$")
ALIAS_RULE = "5-30 letters and numbers"


class ShortenError(Exception):
    """No provider would create the link."""


class AliasTakenError(ShortenError):
    """That alias is unavailable. The caller should offer to pick another."""


def check_alias(alias: str) -> str | None:
    """Return a complaint about the alias, or None when it is usable."""
    if not alias:
        return None  # blank is allowed: the provider generates one
    if not ALIAS_PATTERN.match(alias):
        return f"Custom links must be {ALIAS_RULE}."
    return None


def _ulvis(long_url: str, alias: str) -> str:
    params = {"url": long_url}
    if alias:
        params["custom"] = alias

    response = requests.get(ULVIS_URL, params=params, timeout=TIMEOUT)
    body = response.text.strip()

    if body.startswith("https://") or body.startswith("http://"):
        return body

    # ulvis answers "Error: ..." in plain text with HTTP 200, so the status code
    # proves nothing. Both of its alias complaints are the user's to fix.
    lowered = body.lower()
    if "already taken" in lowered or "spam detected" in lowered:
        raise AliasTakenError(
            "That name is taken. Try another."
            if "already taken" in lowered
            else "ulvis.net rejected that name. Try a different one."
        )
    raise ShortenError(body[:200] or f"ulvis.net gave no answer (HTTP {response.status_code}).")


def _is_gd(long_url: str, alias: str) -> str:
    params = {"format": "json", "url": long_url}
    if alias:
        params["shorturl"] = alias

    response = requests.get(IS_GD_URL, params=params, timeout=TIMEOUT)

    try:
        payload = response.json()
    except ValueError:
        # is.gd returns plain-text errors even when asked for JSON.
        raise ShortenError(response.text.strip()[:200] or "is.gd gave no answer.")

    short_url = payload.get("shorturl")
    if short_url:
        return short_url

    message = str(payload.get("errormessage") or "").strip() or "is.gd rejected the request."
    # 1 = bad long URL, 2 = bad or taken alias, 3 = rate limited, 4 = their end.
    if payload.get("errorcode") == 2:
        raise AliasTakenError(message)
    raise ShortenError(message)


def shorten(long_url: str, alias: str = "") -> str:
    """Shorten long_url, optionally at a chosen alias. Returns the short URL."""
    complaint = check_alias(alias)
    if complaint:
        raise AliasTakenError(complaint)

    problems = []
    for name, provider in (("ulvis.net", _ulvis), ("is.gd", _is_gd)):
        try:
            return provider(long_url, alias)
        except AliasTakenError:
            # The alias is the user's to fix, and every provider would reject it
            # for the same reason. Asking the next one only wastes time.
            raise
        except (ShortenError, requests.RequestException) as exc:
            problems.append(f"{name}: {exc}")

    raise ShortenError("; ".join(problems))
