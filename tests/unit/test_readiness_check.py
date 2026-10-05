"""
app.main.readiness_check's failure path — no real DB involved. The
success path (database actually reachable) is covered as a regression
test in tests/regression/test_request_logging.py since that needs a live
Postgres; this just verifies a connection failure turns into a clean 503
instead of an unhandled exception bubbling out of the endpoint.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.main import readiness_check


async def test_readiness_check_returns_503_when_database_unreachable():
    # AsyncEngine.connect is a read-only attribute on the real engine, so
    # the whole module-level `engine` reference is swapped out instead of
    # patching one of its attributes in place.
    with patch("app.main.engine") as mock_engine:
        mock_engine.connect.side_effect = ConnectionError("boom")
        with pytest.raises(HTTPException) as exc_info:
            await readiness_check()
    assert exc_info.value.status_code == 503
