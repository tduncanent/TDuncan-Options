# TDuncan Options App — VS Code and Streamlit Setup

## 1. Open the new app separately

1. Extract the APP 2 ZIP into its own folder, such as `TDuncan-Options`.
2. In Visual Studio Code, select **File → Open Folder** and open that folder.

## 2. Create the local Python environment

Open **Terminal → New Terminal** in VS Code and run:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. Add your local secrets

1. In `.streamlit`, copy `secrets.toml.example`.
2. Rename the copy to `secrets.toml`.
3. Replace every placeholder with the same APP password and Tastytrade credentials used by the original app.

The real `secrets.toml` is excluded by `.gitignore`; do not commit it.

## 4. Test locally

```powershell
streamlit run app/main.py
```

Confirm the page opens with these defaults:

- Symbols: QQQ, SPY, XSP, XND
- Max Rows: 5,000
- Maximum selectable rows: 10,000
- Spread Widths: 1,2,3

## 5. Push APP 2 to a separate GitHub repository

Create a new, empty GitHub repository without a README, license, or Git ignore file. Then run:

```powershell
git init
git add .
git commit -m "Create TDuncan Options app"
git branch -M main
git remote add origin YOUR_NEW_GITHUB_REPOSITORY_URL
git push -u origin main
```

Before pushing, verify that `.streamlit/secrets.toml` is not listed by `git status`.

## 6. Deploy the second Streamlit app

1. Go to https://share.streamlit.io and select **Create app**.
2. Choose the new APP 2 repository.
3. Select branch `main`.
4. Enter `app/main.py` as the entrypoint file.
5. Open **Advanced settings** and use Python 3.12.
6. Paste the real contents of your local `.streamlit/secrets.toml` into the Streamlit secrets field.
7. Select **Deploy**.

APP 1 and APP 2 will then have separate repositories, Streamlit deployments, URLs, and settings.
