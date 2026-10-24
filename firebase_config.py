import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_FILE = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_FILE",
    str(BASE_DIR / "firebase-service-account.json")
)

if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred)

db = firestore.client()


def verify_id_token(id_token):
    return auth.verify_id_token(id_token)


def create_user_profile(uid, email="", display_name=""):
    ref = db.collection("users").document(uid)
    snap = ref.get()

    if not snap.exists:
        ref.set({
            "uid": uid,
            "email": email,
            "displayName": display_name,
            "storageUsedBytes": 0,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
    else:
        ref.set({
            "email": email,
            "displayName": display_name,
        }, merge=True)

    return ref
