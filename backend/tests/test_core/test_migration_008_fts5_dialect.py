"""#753: migration 008's FTS5 table/triggers must only run on SQLite."""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "008_add_events_fts5.py"


def _load():
    spec = importlib.util.spec_from_file_location("migration_008_fts5", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _op(dialect):
    op = MagicMock()
    op.get_bind.return_value.dialect.name = dialect
    return op


@pytest.mark.parametrize("fn", ["upgrade", "downgrade"])
def test_noop_on_postgres(fn):
    mod = _load()
    op = _op("postgresql")
    with patch.object(mod, "op", op):
        getattr(mod, fn)()
    op.execute.assert_not_called()


@pytest.mark.parametrize("fn,count", [("upgrade", 5), ("downgrade", 4)])
def test_unchanged_on_sqlite(fn, count):
    mod = _load()
    op = _op("sqlite")
    with patch.object(mod, "op", op):
        getattr(mod, fn)()
    assert op.execute.call_count == count
    sql = " ".join(c.args[0] for c in op.execute.call_args_list)
    assert "events_fts" in sql
