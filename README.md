# CloudNest — Firebase Authentication + Firestore + Local Storage

## What this version does

- Firebase Email/Password registration and login
- Firebase ID-token verification in Flask
- Firestore `users/{uid}` profile records
- Flask session after Firebase authentication
- Local file storage under `storage/<uid>/`
- File upload, download and delete
- Folder creation
- Storage usage and quota display
- Responsive dark UI

## 1. Put your service account JSON in this folder

Rename your Firebase Admin SDK JSON file to:

`firebase-service-account.json`

Never commit or upload this file.

## 2. Create `.env`

Copy `.env.example` to `.env` and fill in the Firebase Web App configuration from:

Firebase Console -> Project settings -> Your apps -> CloudNest Web -> SDK setup and configuration

## 3. Install

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If PowerShell blocks activation, you do NOT need to activate the environment. Use the `.venv\Scripts\python.exe` commands above.

## 4. Test Firestore

```powershell
.\.venv\Scripts\python.exe test_firebase.py
```

## 5. Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Open:

http://127.0.0.1:5000

## Firebase Console setup

Authentication -> Sign-in method -> Email/Password -> Enable.

Firestore Database should already be created.

You do not need Firebase Storage for this version. Files are intentionally stored locally.

## Important

The Firebase Admin SDK JSON is a private credential. Do not share it or put it on GitHub.
