from __future__ import annotations

import ctypes
import http.cookiejar
import json
import math
import os
import re
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


SESSION_TTL_SECONDS = 24 * 60 * 60
MAX_SESSION_BYTES = 64 * 1024
MAX_COOKIES = 128
_VAULT_MAGIC = b"SDM_SESSION_V1\0"
_COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,256}$")
_DOMAIN = re.compile(
    r"^\.?(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


class SessionAuthError(ValueError):
    """Raised when browser-session data is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class SessionCookie:
    name: str
    value: str
    domain: str
    path: str
    secure: bool
    host_only: bool
    expiration_date: float | None = None


@dataclass(frozen=True, slots=True)
class BrowserSession:
    cookies: tuple[SessionCookie, ...]
    source_urls: tuple[str, ...]
    user_agent: str
    created_at: float
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def cookie_jar(self) -> http.cookiejar.CookieJar:
        policy = http.cookiejar.DefaultCookiePolicy(
            strict_ns_domain=(
                http.cookiejar.DefaultCookiePolicy.DomainStrictNonDomain
            )
        )
        jar = http.cookiejar.CookieJar(policy=policy)
        now = time.time()
        for item in self.cookies:
            if item.expiration_date is not None and item.expiration_date <= now:
                continue
            domain = item.domain.lstrip(".") if item.host_only else item.domain
            jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=item.name,
                    value=item.value,
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=not item.host_only,
                    domain_initial_dot=(
                        not item.host_only and item.domain.startswith(".")
                    ),
                    path=item.path,
                    path_specified=True,
                    secure=item.secure,
                    expires=(
                        int(item.expiration_date)
                        if item.expiration_date is not None
                        else None
                    ),
                    discard=item.expiration_date is None,
                    comment=None,
                    comment_url=None,
                    rest={"HttpOnly": None},
                    rfc2109=False,
                )
            )
        return jar


Protector = Callable[[bytes], bytes]


def validate_session_payload(
    payload: object,
    *,
    now: float | None = None,
) -> BrowserSession:
    if not isinstance(payload, dict) or not payload.get("enabled"):
        raise SessionAuthError("Secure browser session data is invalid.")

    source_urls = _valid_source_urls(payload.get("source_urls"))
    if not source_urls:
        raise SessionAuthError("Secure browser session has no valid source URL.")

    raw_user_agent = str(payload.get("user_agent", "")).strip()
    if (
        len(raw_user_agent) > 512
        or "\r" in raw_user_agent
        or "\n" in raw_user_agent
    ):
        raise SessionAuthError("Browser session User-Agent is invalid.")

    raw_cookies = payload.get("cookies")
    if not isinstance(raw_cookies, list) or not raw_cookies:
        raise SessionAuthError("No matching browser cookies were supplied.")
    if len(raw_cookies) > MAX_COOKIES:
        raise SessionAuthError("Too many browser cookies were supplied.")

    cookies: list[SessionCookie] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_cookie in raw_cookies:
        cookie = _validate_cookie(raw_cookie, source_urls)
        key = (cookie.name, cookie.domain.casefold(), cookie.path)
        if key in seen:
            continue
        seen.add(key)
        cookies.append(cookie)

    timestamp = float(now if now is not None else time.time())
    session = BrowserSession(
        cookies=tuple(cookies),
        source_urls=tuple(source_urls),
        user_agent=raw_user_agent,
        created_at=timestamp,
        expires_at=timestamp + SESSION_TTL_SECONDS,
    )
    if len(_serialize(session)) > MAX_SESSION_BYTES:
        raise SessionAuthError("Secure browser session data is too large.")
    return session


def store_session_auth(
    database_path: str | Path,
    record_id: str,
    session: BrowserSession,
    *,
    protector: Protector | None = None,
) -> Path:
    raw = _serialize(session)
    encrypted = (protector or _protect_for_current_user)(raw)
    if not encrypted or raw in encrypted:
        raise SessionAuthError("Browser session encryption failed.")

    path = session_auth_path(database_path, record_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(_VAULT_MAGIC + encrypted)
    os.replace(temporary, path)
    return path


def load_session_auth(
    database_path: str | Path,
    record_id: str,
    *,
    unprotector: Protector | None = None,
) -> BrowserSession | None:
    path = session_auth_path(database_path, record_id)
    try:
        stored = path.read_bytes()
    except FileNotFoundError:
        return None
    if not stored.startswith(_VAULT_MAGIC):
        delete_session_auth(database_path, record_id)
        return None
    try:
        raw = (unprotector or _unprotect_for_current_user)(
            stored[len(_VAULT_MAGIC) :]
        )
        session = _deserialize(raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        delete_session_auth(database_path, record_id)
        return None
    if session.is_expired:
        delete_session_auth(database_path, record_id)
        return None
    return session


def delete_session_auth(database_path: str | Path, record_id: str) -> None:
    try:
        session_auth_path(database_path, record_id).unlink(missing_ok=True)
    except OSError:
        pass


def delete_all_session_auth(database_path: str | Path) -> None:
    directory = _vault_directory(database_path)
    if not directory.is_dir():
        return
    for path in directory.glob("*.bin"):
        try:
            path.unlink()
        except OSError:
            pass


def session_auth_path(database_path: str | Path, record_id: str) -> Path:
    safe_record_id = re.sub(r"[^A-Za-z0-9-]", "", str(record_id))
    if not safe_record_id:
        raise SessionAuthError("Invalid download record identifier.")
    return _vault_directory(database_path) / f"{safe_record_id}.bin"


def open_session_url(
    request: urllib.request.Request,
    *,
    session: BrowserSession | None,
    timeout: float,
):
    if session is None:
        return urllib.request.urlopen(request, timeout=timeout)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(session.cookie_jar())
    )
    return opener.open(request, timeout=timeout)


def session_user_agent(session: BrowserSession | None, fallback: str) -> str:
    return session.user_agent if session and session.user_agent else fallback


def _valid_source_urls(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in value[:8]:
        url = str(raw or "").strip()
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or len(url) > 8192
        ):
            continue
        normalized = parsed.geturl()
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _validate_cookie(
    value: object,
    source_urls: list[str],
) -> SessionCookie:
    if not isinstance(value, dict):
        raise SessionAuthError("Browser cookie data is invalid.")
    name = str(value.get("name", ""))
    cookie_value = str(value.get("value", ""))
    domain = str(value.get("domain", "")).strip().lower()
    path = str(value.get("path", "/")).strip() or "/"
    if not _COOKIE_NAME.fullmatch(name):
        raise SessionAuthError("Browser cookie name is invalid.")
    if (
        len(cookie_value) > 4096
        or any(ord(character) < 32 or ord(character) == 127 for character in cookie_value)
        or ";" in cookie_value
    ):
        raise SessionAuthError("Browser cookie value is invalid.")
    if len(domain) > 253 or not _DOMAIN.fullmatch(domain):
        raise SessionAuthError("Browser cookie domain is invalid.")
    if (
        len(path) > 1024
        or not path.startswith("/")
        or "\r" in path
        or "\n" in path
    ):
        raise SessionAuthError("Browser cookie path is invalid.")
    if not _domain_matches_any_source(domain, source_urls):
        raise SessionAuthError("Browser cookie does not match the download site.")

    expiration_value = value.get("expiration_date")
    expiration_date: float | None = None
    if expiration_value is not None:
        try:
            candidate = float(expiration_value)
        except (TypeError, ValueError, OverflowError) as error:
            raise SessionAuthError("Browser cookie expiration is invalid.") from error
        if math.isfinite(candidate) and candidate > 0:
            expiration_date = candidate

    return SessionCookie(
        name=name,
        value=cookie_value,
        domain=domain,
        path=path,
        secure=bool(value.get("secure")),
        host_only=bool(value.get("host_only")),
        expiration_date=expiration_date,
    )


def _domain_matches_any_source(domain: str, urls: list[str]) -> bool:
    cookie_domain = domain.lstrip(".")
    for url in urls:
        hostname = (urlsplit(url).hostname or "").lower()
        if hostname == cookie_domain or hostname.endswith(f".{cookie_domain}"):
            return True
    return False


def _vault_directory(database_path: str | Path) -> Path:
    return Path(database_path).parent / "session_vault"


def _serialize(session: BrowserSession) -> bytes:
    payload = {
        "cookies": [asdict(cookie) for cookie in session.cookies],
        "source_urls": list(session.source_urls),
        "user_agent": session.user_agent,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _deserialize(raw: bytes) -> BrowserSession:
    payload = json.loads(raw.decode("utf-8"))
    cookies = tuple(SessionCookie(**item) for item in payload["cookies"])
    return BrowserSession(
        cookies=cookies,
        source_urls=tuple(str(url) for url in payload["source_urls"]),
        user_agent=str(payload.get("user_agent", "")),
        created_at=float(payload["created_at"]),
        expires_at=float(payload["expires_at"]),
    )


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _protect_for_current_user(data: bytes) -> bytes:
    if os.name != "nt":
        raise SessionAuthError(
            "Secure Session Bridge requires Windows DPAPI."
        )
    source, source_buffer = _blob(data)
    output = _DataBlob()
    protect = ctypes.windll.crypt32.CryptProtectData
    protect.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_DataBlob),
    ]
    protect.restype = ctypes.c_int
    result = protect(
        ctypes.byref(source),
        "SDM Secure Session",
        None,
        None,
        None,
        0x01,
        ctypes.byref(output),
    )
    if not result:
        raise SessionAuthError("Windows could not encrypt the browser session.")
    del source_buffer
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        _local_free(output.pbData)


def _unprotect_for_current_user(data: bytes) -> bytes:
    if os.name != "nt":
        raise SessionAuthError(
            "Secure Session Bridge requires Windows DPAPI."
        )
    source, source_buffer = _blob(data)
    output = _DataBlob()
    unprotect = ctypes.windll.crypt32.CryptUnprotectData
    unprotect.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_DataBlob),
    ]
    unprotect.restype = ctypes.c_int
    result = unprotect(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(output),
    )
    if not result:
        raise SessionAuthError("Windows could not decrypt the browser session.")
    del source_buffer
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        _local_free(output.pbData)


def _local_free(pointer) -> None:
    local_free = ctypes.windll.kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    local_free(pointer)
