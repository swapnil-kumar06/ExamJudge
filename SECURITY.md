# Security checklist for ExamJudge

## Before deploying

- Store `GEMINI_API_KEY`, `APP_PASSWORD`, and optionally `GEMINI_MODEL` in the deployment platform's **Secrets** panel.
- Never commit `.streamlit/secrets.toml`, `.env`, a copied key, a screenshot of a key, or a key in a log.
- Use a long, randomly generated `APP_PASSWORD`, and share it only with intended testers. Rotate it if shared too widely.
- Configure provider-side quota/usage limits. The app's per-session budget is a best-effort guard and can be bypassed by creating multiple sessions.
- Test with synthetic/anonymised answers first. Obtain institutional approval before sending identifiable student data to an external model provider.

## If a key may have leaked

1. Revoke the exposed Gemini key in the provider console immediately.
2. Create a replacement key.
3. Update `GEMINI_API_KEY` in Streamlit Secrets and reboot the app.
4. Review provider usage for unexpected requests and rotate `APP_PASSWORD` if that may also have been exposed.
5. If a secret was committed to Git, deleting the file is not enough; rotate the key even if the commit history is rewritten.

## What this deployment does and does not protect

The application reads the Gemini key server-side and does not expose it as a user-editable field. The Gemini endpoint is fixed, error messages are sanitised, student content is bounded and encoded as data in grading prompts, and a shared-password gate is required whenever a server-side Gemini key is configured. Upload size, PDF page count, extracted characters, per-batch answers, and estimated per-session model calls are limited.

This is suitable as a guarded student project demo, not as a production student-records system. A shared password is not per-user authentication, the session usage guard is not a global rate limiter, model output is not guaranteed correct, and the platform owner remains responsible for access control, quotas, privacy compliance, and human review.
