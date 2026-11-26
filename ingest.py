import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

ROOT_DIR = Path(__file__).resolve().parent
DOCS_DIR = ROOT_DIR / "docs"
STORE_NAME_FILE = ROOT_DIR / "store_name.txt"
POLL_INTERVAL_SECONDS = 5


def _document_names(client: Any, store_name: str) -> set[str]:
    names: set[str] = set()
    documents = client.file_search_stores.documents.list(parent=store_name)
    for document in documents:
        display_name = getattr(document, "display_name", None)
        if display_name:
            names.add(display_name)
    return names


def _wait_for_operation(client: Any, operation: Any, file_name: str) -> Any:
    while not operation.done:
        print(f"  Indexing {file_name}...", flush=True)
        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)
    error = getattr(operation, "error", None)
    if error:
        raise RuntimeError(str(error))
    return operation


def _delete_existing_store(client: Any) -> None:
    if not STORE_NAME_FILE.exists():
        return
    store_name = STORE_NAME_FILE.read_text(encoding="utf-8").strip()
    if store_name:
        print(f"Deleting existing store {store_name}...", flush=True)
        client.file_search_stores.delete(
            name=store_name,
            config={"force": True},
        )
    STORE_NAME_FILE.unlink(missing_ok=True)


def ingest(reset: bool = False) -> int:
    load_dotenv(ROOT_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is missing. Add it to the local .env file.", file=sys.stderr)
        return 1

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key)

    if reset:
        _delete_existing_store(client)

    if STORE_NAME_FILE.exists():
        store_name = STORE_NAME_FILE.read_text(encoding="utf-8").strip()
        if store_name:
            print(f"Using existing File Search store {store_name}.", flush=True)
        else:
            store_name = ""
    else:
        store_name = ""

    if not store_name:
        store = client.file_search_stores.create(
            config={
                "display_name": "coep-digital-twin-store",
                "embedding_model": "models/gemini-embedding-2",
            }
        )
        store_name = store.name
        STORE_NAME_FILE.write_text(f"{store_name}\n", encoding="utf-8")
        print(f"Created File Search store {store_name}.", flush=True)

    # Use the remote document list so reruns do not duplicate completed uploads.
    try:
        existing_names = _document_names(client, store_name)
    except Exception as exc:
        print(f"Error: couldn't verify existing documents: {exc}", file=sys.stderr)
        return 1

    files = sorted(
        path for path in DOCS_DIR.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    if not files:
        print(f"No files found in {DOCS_DIR}. Add documents, then run ingest again.")
        return 0

    failures = 0
    for path in files:
        if path.name in existing_names:
            print(f"Skipping already uploaded: {path.name}")
            continue

        print(f"Uploading {path.name}...", flush=True)
        try:
            # Upload directly to the persistent store instead of the temporary Files API.
            operation = client.file_search_stores.upload_to_file_search_store(
                file=str(path),
                file_search_store_name=store_name,
                config={"display_name": path.name},
            )
            _wait_for_operation(client, operation, path.name)
            existing_names.add(path.name)
            print(f"Indexed {path.name}.", flush=True)
        except Exception as exc:
            failures += 1
            print(f"Error indexing {path.name}: {exc}", file=sys.stderr, flush=True)

    if failures:
        print(f"Finished with {failures} file error(s). Successful uploads are saved.")
        return 1
    print(f"Ingestion complete. Store name saved in {STORE_NAME_FILE.name}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Index documents in the Gemini File Search store.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing store and create a fresh one before uploading.",
    )
    args = parser.parse_args()
    return ingest(reset=args.reset)


if __name__ == "__main__":
    raise SystemExit(main())