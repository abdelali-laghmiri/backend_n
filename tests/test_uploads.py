from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.shared import uploads as uploads_module


class ManagedUploadsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_uploads_dir = uploads_module.UPLOADS_DIR
        uploads_module.UPLOADS_DIR = Path(self.temp_dir.name) / "uploads"

    def tearDown(self) -> None:
        uploads_module.UPLOADS_DIR = self.original_uploads_dir
        self.temp_dir.cleanup()

    def test_ensure_uploads_dir_exists_creates_missing_root(self) -> None:
        self.assertFalse(uploads_module.UPLOADS_DIR.exists())

        created_path = uploads_module.ensure_uploads_dir_exists()

        self.assertEqual(created_path, uploads_module.UPLOADS_DIR)
        self.assertTrue(created_path.exists())
        self.assertTrue(created_path.is_dir())

    def test_static_mount_responds_when_uploads_root_starts_missing(self) -> None:
        app = FastAPI()
        uploads_module.ensure_uploads_dir_exists()
        app.mount(
            "/static/uploads",
            StaticFiles(directory=str(uploads_module.UPLOADS_DIR), check_dir=False),
            name="uploads",
        )

        with TestClient(app) as client:
            response = client.get("/static/uploads/missing-file.txt")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
