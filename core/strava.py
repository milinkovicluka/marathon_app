"""Pull activities from Strava (Garmin -> Strava auto-upload -> this app).

Setup is once: create an API app at https://www.strava.com/settings/api with
"localhost" as the callback domain, then connect from the app. Keys and
tokens are kept in strava.json next to the database (ignored by git).
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, tzinfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from core.fit_import import ImportResult, looks_like_same_workout
from core.models import Activity, ActivityType, start_source_id
from core.storage import Storage

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/strava"
PAGE_SIZE = 200

_TYPE_BY_SPORT: dict[str, ActivityType] = {
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "Ride": "bike",
    "VirtualRide": "bike",
    "GravelRide": "bike",
    "MountainBikeRide": "bike",
    "EBikeRide": "bike",
    "EMountainBikeRide": "bike",
    "WeightTraining": "gym",
    "Workout": "gym",
    "Crossfit": "gym",
}

# (method, url, form or query fields, bearer token) -> decoded JSON
HttpCall = Callable[[str, str, Mapping[str, Any], str | None], Any]


class StravaError(Exception):
    pass


def http_json(
    method: str, url: str, fields: Mapping[str, Any], token: str | None
) -> Any:
    encoded = urllib.parse.urlencode(fields)
    data = None
    if method == "GET":
        url = f"{url}?{encoded}" if encoded else url
    else:
        data = encoded.encode()
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:200]
        raise StravaError(f"Strava answered {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise StravaError(f"Can't reach Strava: {error.reason}") from error


@dataclass
class StravaSettings:
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: int = 0
    # Start of the newest synced activity (epoch seconds); the next sync
    # asks only for newer ones. 0 = everything.
    synced_until: int = 0

    @property
    def has_app(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def connected(self) -> bool:
        return self.has_app and bool(self.refresh_token)

    @classmethod
    def load(cls, path: Path) -> "StravaSettings":
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            return cls()
        known = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        return cls(**known)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))
        os.chmod(path, 0o600)


def authorize_url(client_id: str) -> str:
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": "activity:read_all",
        }
    )


def wait_for_code(timeout_seconds: float = 180) -> str:
    """Serve the one redirect Strava makes after you approve, return its code."""
    received: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server name)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            received.update({key: values[0] for key, values in query.items()})
            ok = "code" in received
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            message = (
                "Strava is connected. You can close this tab."
                if ok
                else "Strava was not connected. You can close this tab."
            )
            self.wfile.write(f"<p style='font:16px sans-serif'>{message}</p>".encode())

        def log_message(self, *args: object) -> None:
            pass

    deadline = time.monotonic() + timeout_seconds
    with HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler) as server:
        while not received and time.monotonic() < deadline:
            server.timeout = max(0.1, deadline - time.monotonic())
            server.handle_request()
    if "code" not in received:
        reason = received.get("error", "no answer from the browser in time")
        raise StravaError(f"Strava login didn't finish: {reason}")
    if "activity:read" not in received.get("scope", ""):
        raise StravaError("Please allow access to your activities on the Strava page.")
    return received["code"]


def _store_tokens(settings: StravaSettings, answer: Mapping[str, Any]) -> None:
    settings.access_token = answer["access_token"]
    settings.refresh_token = answer["refresh_token"]
    settings.expires_at = int(answer["expires_at"])


def exchange_code(settings: StravaSettings, code: str, http: HttpCall = http_json) -> None:
    answer = http(
        "POST",
        TOKEN_URL,
        {
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        None,
    )
    _store_tokens(settings, answer)


def fresh_access_token(
    settings: StravaSettings, http: HttpCall = http_json, now: float | None = None
) -> str:
    now = time.time() if now is None else now
    if settings.access_token and settings.expires_at > now + 60:
        return settings.access_token
    answer = http(
        "POST",
        TOKEN_URL,
        {
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "refresh_token": settings.refresh_token,
            "grant_type": "refresh_token",
        },
        None,
    )
    _store_tokens(settings, answer)
    return settings.access_token


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def activity_from_strava(summary: Mapping[str, Any], local_zone: tzinfo | None = None) -> Activity:
    start = _parse_utc(summary["start_date"])
    sport = summary.get("sport_type") or summary.get("type") or ""
    seconds = summary.get("moving_time") or summary.get("elapsed_time") or 0
    return Activity(
        date=start.astimezone(local_zone).date(),
        type=_TYPE_BY_SPORT.get(sport, "sport"),
        distance_km=(summary.get("distance") or 0) / 1000,
        duration=timedelta(seconds=round(seconds)),
        notes=str(summary.get("name") or sport).strip(),
        source_id=start_source_id(start),
    )


def iter_activities(
    token: str, after: int, http: HttpCall = http_json
) -> Iterator[Mapping[str, Any]]:
    page = 1
    while True:
        batch = http(
            "GET",
            ACTIVITIES_URL,
            {"after": after, "per_page": PAGE_SIZE, "page": page},
            token,
        )
        if not batch:
            return
        yield from batch
        page += 1


def sync(
    storage: Storage,
    settings: StravaSettings,
    http: HttpCall = http_json,
    local_zone: tzinfo | None = None,
) -> ImportResult:
    """Add Strava activities newer than the last sync. Updates settings."""
    result = ImportResult()
    token = fresh_access_token(settings, http)
    existing = storage.list_activities()
    for summary in iter_activities(token, settings.synced_until, http):
        start = int(_parse_utc(summary["start_date"]).timestamp())
        label = Path(f"{summary.get('name', 'activity')} ({summary.get('start_date', '')[:10]})")
        try:
            activity = activity_from_strava(summary, local_zone)
        except (KeyError, ValueError) as error:
            result.failed.append((label, str(error)))
        else:
            if storage.has_source(activity.source_id or ""):
                result.already_imported.append(label)
            else:
                saved = storage.add(activity)
                result.imported.append(saved)
                result.possible_duplicates.extend(
                    (saved, logged)
                    for logged in existing
                    if looks_like_same_workout(saved, logged)
                )
        settings.synced_until = max(settings.synced_until, start)
    return result
