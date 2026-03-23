import os
import pytest
import tempfile
from db import Database


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    yield database
    database.close()


def test_creates_tables(db):
    # Tables exist if we can insert without error
    db.save_transcription("hello world", 1.5)


def test_save_and_query_transcription(db):
    db.save_transcription("hello world", 2.0)
    results, total = db.get_transcriptions(page=1, search="")
    assert total == 1
    assert results[0]["text"] == "hello world"
    assert results[0]["duration"] == 2.0
    assert "created_at" in results[0]


def test_search_transcription(db):
    db.save_transcription("good morning", 1.0)
    db.save_transcription("good night", 1.0)
    results, total = db.get_transcriptions(page=1, search="morning")
    assert total == 1
    assert results[0]["text"] == "good morning"


def test_pagination(db):
    for i in range(55):
        db.save_transcription(f"text {i}", 1.0)
    results, total = db.get_transcriptions(page=1, search="")
    assert total == 55
    assert len(results) == 50  # page size
    results2, _ = db.get_transcriptions(page=2, search="")
    assert len(results2) == 5


def test_settings_get_set(db):
    db.set_setting("pill_x", "100")
    assert db.get_setting("pill_x") == "100"


def test_settings_default(db):
    assert db.get_setting("missing_key", default="42") == "42"


def test_thread_safety(db):
    import threading
    errors = []
    def worker():
        try:
            db.save_transcription("concurrent", 0.5)
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
    _, total = db.get_transcriptions(1, "")
    assert total == 10
