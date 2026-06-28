from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ["DATABASE_URL"] = "sqlite://"

from app.core import database as database_module
from app.core.config import settings
from app.shared.responses import HealthDetailedResponse, HealthResponse


def _check_database() -> str:
    try:
        with database_module.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "unconnected"


app = FastAPI()


@app.get(
    "/",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    summary="Service root",
)
def read_root() -> HealthResponse:
    return HealthResponse(
        status="ok",
        detail="HR management backend skeleton is running.",
    )


@app.get(
    "/health",
    tags=["Health"],
    summary="Application health check with database connectivity",
)
def health_check() -> JSONResponse:
    db_status = _check_database()
    overall = "ok" if db_status == "connected" else "unhealthy"
    http_code = status.HTTP_200_OK if db_status == "connected" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        content=HealthDetailedResponse(
            status=overall,
            detail="Service is healthy." if db_status == "connected" else "Database is unreachable.",
            database=db_status,
            environment=settings.app_env.value,
            version=settings.project_version,
        ).model_dump(),
        status_code=http_code,
    )


class HealthTests(unittest.TestCase):
    def test_root_health_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["detail"], "HR management backend skeleton is running.")

    def test_detailed_health_db_connected(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["database"], "connected")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["detail"], "Service is healthy.")
        self.assertIn("environment", data)
        self.assertIn("version", data)

    def test_detailed_health_db_unreachable(self) -> None:
        with patch("app.core.database.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception("DB unavailable")
            with TestClient(app) as client:
                response = client.get("/health")
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["database"], "unconnected")
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["detail"], "Database is unreachable.")


if __name__ == "__main__":
    unittest.main()
