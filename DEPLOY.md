# Deploying the hosted upload app (Streamlit Community Cloud)

This gives you a real URL where you (and anyone you give the password to) can
upload an export and download the report — no local install.

> The app executes on Streamlit's servers. A **raw** upload is de-identified
> there and the raw copy discarded, but it does touch that infrastructure for
> a few seconds. Prefer uploading files that are already de-identified. The
> password gate is the only thing keeping the app from being world-open, so
> pick a strong one.

## One-time setup

1. Go to <https://share.streamlit.io> and sign in with the GitHub account that
   owns `ahabalshehri/laboratory-statistics`.
2. **Create app** → **Deploy a public app from GitHub**:
   - Repository: `ahabalshehri/laboratory-statistics`
   - Branch: `master`
   - Main file path: `app.py`
3. Open **Advanced settings → Secrets** and paste:
   ```toml
   app_password = "a-long-random-passphrase"
   ```
   Setting this both (a) turns on the login prompt and (b) forces server-side
   de-identification (the "hosted" safety mode).
4. **Deploy**. First build takes a few minutes (installs `requirements.txt`).
5. Recommended: in the app's **Settings → Sharing**, set it to **"Only
   specific people can view this app"** and add the email addresses that
   should have access. That adds a Google/GitHub sign-in on top of the
   password.

## Using it

- URL looks like `https://<something>-<hash>.streamlit.app`.
- Enter the password → pick **"Ayenati External Report"** in the sidebar →
  upload a `.xlsx` or paste a link → download the PDF / Excel / HTML / Markdown.

## Updating

Every push to `master` redeploys the app automatically. To change the
password, edit the secret in the app's settings (no redeploy needed).

## Notes

- `runtime.txt` pins Python 3.12; `requirements.txt` is the full dependency
  set (Streamlit, pandas, reportlab, Pillow, …).
- Free tier: apps sleep after inactivity and wake on the next visit (~30 s).
- Without the `app_password` secret the app runs open with no prompt — that
  mode is only meant for `streamlit run app.py` on your own machine.
