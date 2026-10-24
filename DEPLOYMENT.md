# Secure free deployment (Gemini + Streamlit Community Cloud)

## 1. Create a Gemini API key
1. Open Google AI Studio and create an API key for your project.
2. Do not paste the key into `app.py`, into any screenshot, or into a public GitHub file.
3. Check the Google AI Studio terms and quota settings for the account that owns the key.

## 2. Push the project to GitHub
Upload the contents of this folder to a repository. Public source code is okay; secret values must not be in the repository. The `.gitignore` excludes local `.streamlit/secrets.toml` and `.env` files. Before pushing, run `git status` and verify no real key or local secrets file is staged.

## 3. Deploy on Streamlit Community Cloud
1. Create a Streamlit Community Cloud app and select this repository, branch, and `app.py`.
2. Open the deployed app's **Settings → Secrets**.
3. Add the following TOML, replacing the placeholders:

   ```toml
   GEMINI_API_KEY = "your-real-Gemini-key"
   APP_PASSWORD = "a-long-random-password-only-your-users-know"
   GEMINI_MODEL = "gemini-2.5-flash"
   ```

4. Save and reboot the app. Use a Gemini model currently available to your API key; if the default name is not available, edit `GEMINI_MODEL` in Secrets. Do not put an API key into the dashboard UI; the UI intentionally has no API-key input field.
5. Share the app URL and the app password only with intended testers.

## 4. Local run

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your Gemini key and a strong APP_PASSWORD
streamlit run app.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your real values
streamlit run app.py
```

Local offline mode works without a key or app password. If `GEMINI_API_KEY` is configured, `APP_PASSWORD` is mandatory; the app refuses to start in Gemini mode without it.

## Security model and limits

- `GEMINI_API_KEY` is read on the Python server from Streamlit Secrets / environment variables. It is never placed into a text field, sent to browser JavaScript, or returned in the app output.
- The API endpoint is fixed to Google's OpenAI-compatible API. Visitors cannot change the endpoint and redirect the server key to another host. `GEMINI_MODEL` is owner-controlled in Secrets.
- The app uses a shared password gate and a basic per-session estimated-call budget. These help with a classroom demo but are **not** user accounts, strong institutional auth, or a global usage quota. A motivated user with the password can consume API quota. Add provider-side quota/budget controls; revoke and replace the key if you suspect misuse.
- Do not rely on a shared password for confidential exam scripts. Use anonymised answers, obtain institutional approval, and check Google data-processing/retention terms before sending student work to an external API.
- Uploads have a 10 MB limit, PDFs are limited to 40 pages and 60,000 extracted characters, batches to 10 answers, and prompt input lengths are bounded.
- The no-key baseline is a weak keyword heuristic and must not be used for final grading. Human review is required before high-stakes grading decisions.

## Troubleshooting
- **Authentication failed:** confirm `GEMINI_API_KEY` is correct and has not been revoked. Never paste it into a support chat.
- **Quota/rate limit:** wait and inspect Google AI Studio quota; reduce batch and audit runs.
- **Model rejected:** update `GEMINI_MODEL` to a model currently enabled for your key and reboot the app.
- **App refuses to start:** when `GEMINI_API_KEY` exists, `APP_PASSWORD` must also be set.
