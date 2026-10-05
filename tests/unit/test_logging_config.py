"""
RequestIdFilter and configure_logging — no DB, no HTTP. The actual log
output from real requests is covered in
tests/regression/test_request_logging.py instead, since the request id
only gets set by the middleware in app/main.py.
"""
import logging

from app.logging_config import RequestIdFilter, configure_logging
from app.request_context import request_id_var


def test_request_id_filter_defaults_to_placeholder():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)
    assert RequestIdFilter().filter(record) is True
    assert record.request_id == "-"


def test_request_id_filter_uses_current_context_value():
    token = request_id_var.set("abc-123")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)
        RequestIdFilter().filter(record)
        assert record.request_id == "abc-123"
    finally:
        request_id_var.reset(token)


def test_configure_logging_sets_root_level():
    configure_logging("DEBUG")
    try:
        assert logging.getLogger().level == logging.DEBUG
    finally:
        configure_logging("INFO")  # restore, so later tests see the normal level
