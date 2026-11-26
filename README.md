# COEP-Digital-Twin

## COEP Technological University Digital Twin Chat

A small FastAPI chat app that answers from a Google Gemini File Search store and shows the cited source filenames. The API key remains on the server. Document indexing uses Google's direct upload-to-store API, so indexed content persists in the File Search store rather than depending on temporary Files API uploads.

## Requirements

- Python 3.10 or newer
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- The documents you want indexed

If the key previously pasted into chat was real, revoke it in AI Studio and create a replacement. Never paste the new key into chat or commit it.

## Run locally

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

2. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`, then set `GEMINI_API_KEY` to your new key. The default generation model is `gemini-3.6-flash`; override `GEMINI_MODEL` only with a model currently supported for File Search.

   ```powershell
   Copy-Item .env.example .env
   ```

4. Put your PDF, DOCX, TXT, or other supported files in `docs/`. Local documents are ignored by Git by default.

5. Create and populate the persistent File Search store:

   ```powershell
   python ingest.py
   ```

   Ingestion writes the store name to `store_name.txt`, polls each operation until processing completes, and skips filenames already present in the store. To deliberately delete and rebuild that store:

   ```powershell
   python ingest.py --reset
   ```

6. Start the server:

   ```powershell
   uvicorn app:app --reload
   ```

7. Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The API is available at `POST /chat` and accepts `{"message":"...","history":[]}`. Its response is `{"answer":"...","sources":["filename.pdf"]}`. Run the local checks with `pytest -q`.

## Add documents later

Copy new files into `docs/` and run `python ingest.py` again. Existing filenames already in the store are skipped. To replace a file under the same name, delete that document from the File Search store first or run `python ingest.py --reset` to rebuild the whole store.

Scanned/image-only PDFs need OCR before indexing. File Search cannot retrieve text that is only present as an unrecognized image.

## Embed the chat

Host this app at a stable HTTPS URL, then add this snippet to the page where the floating launcher should appear:

```html
<script
  src="https://YOUR_CHATBOT_DOMAIN/widget.js"
  data-chat-url="https://YOUR_CHATBOT_DOMAIN"
  defer
></script>
```

Replace `YOUR_CHATBOT_DOMAIN` with the deployed app's origin. The script opens the chat in a floating iframe; keep the chat app's domain available and set `ALLOWED_ORIGINS` to the permitted website origins if that website also calls the API directly.

## Deploy

Deploy to Render, Railway, or a VPS with Python installed. Use `pip install -r requirements.txt` as the build/install command and `uvicorn app:app --host 0.0.0.0 --port $PORT` as the start command (on a VPS, use a fixed port such as `8000`). Set `GEMINI_API_KEY`, `GEMINI_MODEL`, and `ALLOWED_ORIGINS` in the host's secret/environment settings. Set `FILE_SEARCH_STORE_NAME` to the value in your local `store_name.txt`; the environment variable is useful when the host does not persist local files. The PDFs are intentionally excluded from Git: once indexed, their content persists in Google's managed File Search store, so the deployed app needs the store name and API key, not local copies of the PDFs. If deploying to a different Google project, run ingestion there with the documents available locally, then configure that project's store name. Do not commit `.env`, store credentials, or private documents.

The built-in rate limiter is process-local. For multi-instance production deployments, use a shared rate-limit backend or an edge/API gateway limit.

## Troubleshooting

- **No answer from a scanned PDF:** run OCR, save a text-searchable PDF, and re-index it.
- **Confirm retrieval:** ask a question whose answer is explicit in one indexed file; a successful response should include that filename under the answer. Questions with no cited file deliberately return `I don't have that information.`
- **No store configured:** make sure `store_name.txt` exists locally or set `FILE_SEARCH_STORE_NAME`, then restart the server.
- **401/403:** check that the replacement API key is valid, enabled for the Gemini API, and set in the active environment. Keep it only in `.env` or the host's secret manager.
- **404 or store not found:** verify the store name belongs to the same Google project as the API key. Re-run ingestion if you reset or deleted the store.
- **429:** wait and retry. The app limits each client IP to 10 chat requests per minute, in addition to Google API quotas.
- **File processing errors:** check the printed filename/error, file type and size, network, and project File Search quota. Run `python ingest.py` again; successfully indexed files are retained and skipped.
- **No answer for a scanned page:** File Search needs OCR-readable text for text-based retrieval. The fallback is also used when the response has no file citation.

## API behavior

`POST /chat` accepts a message up to 2,000 characters and up to 12 short history entries. It uses the current Google GenAI Interactions API File Search tool with the persistent store and does not send the Gemini key to the browser. CORS allows `https://yourwebsite.com` by default; set `ALLOWED_ORIGINS` to a comma-separated list of exact origins for your deployment.
