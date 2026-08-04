import os
import shutil
import tempfile
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("STORAGE_PATH", tempfile.mkdtemp(prefix="digital-mentor-test-storage-"))
os.environ.setdefault("MOCK_ANALYSIS_STEP_DELAY", "0.01")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    storage_root = Path(os.environ["STORAGE_PATH"])
    for directory in ("documents", "extracted", "reports"):
        path = storage_root / directory
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)

    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
