from __future__ import annotations

import time
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from sdm.session_auth import (
    BrowserSession,
    SessionAuthError,
    SessionCookie,
    delete_session_auth,
    load_session_auth,
    session_auth_path,
    store_session_auth,
    validate_session_payload,
)
from sdm.database import DownloadRepository


def _xor(value: bytes) -> bytes:
    return bytes(byte ^ 0xA5 for byte in value)


class SessionAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "enabled": True,
            "source_urls": [
                "https://chatgpt.com/backend-api/files/content?id=7"
            ],
            "user_agent": "Mozilla/5.0 SDM-Test",
            "cookies": [
                {
                    "name": "__Secure-session",
                    "value": "private-token",
                    "domain": "chatgpt.com",
                    "path": "/backend-api/",
                    "secure": True,
                    "host_only": True,
                    "expiration_date": time.time() + 3600,
                }
            ],
        }

    def test_session_round_trip_is_encrypted_and_not_plaintext(self) -> None:
        with TemporaryDirectory() as folder:
            database = Path(folder) / "downloads.db"
            session = validate_session_payload(self.payload, now=time.time())
            path = store_session_auth(
                database,
                "record-1",
                session,
                protector=_xor,
            )
            self.assertNotIn(b"private-token", path.read_bytes())

            restored = load_session_auth(
                database,
                "record-1",
                unprotector=_xor,
            )
            self.assertEqual(restored, session)

    def test_expired_session_is_deleted(self) -> None:
        with TemporaryDirectory() as folder:
            database = Path(folder) / "downloads.db"
            session = BrowserSession(
                cookies=(
                    SessionCookie(
                        name="sid",
                        value="expired",
                        domain="example.com",
                        path="/",
                        secure=False,
                        host_only=True,
                    ),
                ),
                source_urls=("http://example.com/file",),
                user_agent="",
                created_at=1,
                expires_at=2,
            )
            store_session_auth(
                database,
                "expired-record",
                session,
                protector=_xor,
            )
            self.assertIsNone(
                load_session_auth(
                    database,
                    "expired-record",
                    unprotector=_xor,
                )
            )
            self.assertFalse(
                session_auth_path(database, "expired-record").exists()
            )

    def test_cookie_is_not_sent_to_another_domain_or_path(self) -> None:
        session = validate_session_payload(self.payload)
        allowed = urllib.request.Request(
            "https://chatgpt.com/backend-api/files/content?id=7"
        )
        wrong_path = urllib.request.Request("https://chatgpt.com/public/file")
        wrong_host = urllib.request.Request(
            "https://cdn.example.com/backend-api/files/content"
        )
        for request in (allowed, wrong_path, wrong_host):
            session.cookie_jar().add_cookie_header(request)

        self.assertEqual(
            allowed.get_header("Cookie"),
            "__Secure-session=private-token",
        )
        self.assertIsNone(wrong_path.get_header("Cookie"))
        self.assertIsNone(wrong_host.get_header("Cookie"))

    def test_cookie_domain_must_match_a_selected_download_site(self) -> None:
        self.payload["cookies"][0]["domain"] = ".evil.example"
        with self.assertRaises(SessionAuthError):
            validate_session_payload(self.payload)

    def test_control_characters_are_rejected(self) -> None:
        self.payload["cookies"][0]["value"] = "safe\r\nX-Leak: yes"
        with self.assertRaises(SessionAuthError):
            validate_session_payload(self.payload)

    def test_vault_delete_is_idempotent(self) -> None:
        with TemporaryDirectory() as folder:
            database = Path(folder) / "downloads.db"
            session = validate_session_payload(self.payload)
            store_session_auth(
                database,
                "record-delete",
                session,
                protector=_xor,
            )
            delete_session_auth(database, "record-delete")
            delete_session_auth(database, "record-delete")
            self.assertFalse(
                session_auth_path(database, "record-delete").exists()
            )

    def test_deleting_download_history_removes_session_vault_files(self) -> None:
        with TemporaryDirectory() as folder:
            database = Path(folder) / "downloads.db"
            repository = DownloadRepository(database)
            record = repository.create_download(
                url="https://example.com/private.zip",
                filename="private.zip",
                folder=folder,
            )
            path = session_auth_path(database, record.id)
            path.parent.mkdir(parents=True)
            path.write_bytes(b"test-vault")

            repository.delete(record.id)

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
