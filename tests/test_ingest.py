from types import SimpleNamespace

import ingest


class FakeDocuments:
    def list(self, parent: str) -> list[SimpleNamespace]:
        assert parent == "fileSearchStores/test"
        return [SimpleNamespace(display_name="already-indexed.pdf")]


class FakeStores:
    def __init__(self) -> None:
        self.documents = FakeDocuments()
        self.uploads: list[dict[str, object]] = []

    def upload_to_file_search_store(self, **kwargs: object) -> SimpleNamespace:
        self.uploads.append(kwargs)
        return SimpleNamespace(done=True, error=None)


def test_ingestion_skips_existing_and_uploads_new_files(tmp_path, monkeypatch, capsys) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / ".gitkeep").write_text("", encoding="utf-8")
    (docs_dir / "already-indexed.pdf").write_bytes(b"old")
    new_file = docs_dir / "new-notes.txt"
    new_file.write_text("new content", encoding="utf-8")
    store_file = tmp_path / "store_name.txt"
    store_file.write_text("fileSearchStores/test\n", encoding="utf-8")
    stores = FakeStores()

    monkeypatch.setattr(ingest, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(ingest, "STORE_NAME_FILE", store_file)
    monkeypatch.setattr(ingest.genai, "Client", lambda api_key: SimpleNamespace(file_search_stores=stores))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    result = ingest.ingest()

    output = capsys.readouterr().out
    assert result == 0
    assert "Skipping already uploaded: already-indexed.pdf" in output
    assert "Indexed new-notes.txt." in output
    assert len(stores.uploads) == 1
    assert stores.uploads[0]["file"] == str(new_file)
    assert stores.uploads[0]["file_search_store_name"] == "fileSearchStores/test"
    assert stores.uploads[0]["config"] == {"display_name": "new-notes.txt"}