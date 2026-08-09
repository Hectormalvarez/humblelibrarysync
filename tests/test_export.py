"""
Tests for the Export router – POST /export/manifest/download.
"""

from humble_sync.db.queries import add_or_update_booklog_entry
from humble_sync.utils.text import normalize_title


class TestExportManifest:
    """POST /export/manifest/download returns a plain-text manifest."""

    def test_export_empty_booklog(self, client):
        """With no entries, the manifest should contain only header lines."""
        resp = client.post("/export/manifest/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert "booklog_manifest.txt" in resp.headers.get("content-disposition", "")
        text = resp.text
        assert "# Book Log Manifest" in text
        assert "Total entries: 0" in text

    def test_export_with_entries(self, client):
        """With entries, the manifest should contain each title."""
        from humble_sync.db.database import SessionLocal
        from tests.conftest import TEST_USER_ID

        db = SessionLocal()
        try:
            add_or_update_booklog_entry(
                db,
                user_id=TEST_USER_ID,
                title="Dune, Vol. 1",
                norm_title=normalize_title("Dune, Vol. 1"),
                status="wishlist",
                author_or_publisher="Frank Herbert",
            )
            add_or_update_booklog_entry(
                db,
                user_id=TEST_USER_ID,
                title="Foundation",
                norm_title=normalize_title("Foundation"),
                status="finished",
            )
            db.commit()
        finally:
            db.close()

        resp = client.post("/export/manifest/download")
        assert resp.status_code == 200
        text = resp.text
        assert "Total entries: 2" in text
        assert "Dune, Vol. 1" in text
        assert "Foundation" in text
        assert "[wishlist]" in text
        assert "[finished]" in text
        assert "Frank Herbert" in text

    def test_export_content_disposition(self, client):
        """Verify the Content-Disposition header specifies attachment."""
        resp = client.post("/export/manifest/download")
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "booklog_manifest.txt" in cd