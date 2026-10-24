from firebase_config import db

print("Testing CloudNest Firebase connection...")
doc = db.collection("cloudnest_test").document("connection")
doc.set({"project": "CloudNest", "status": "connected"})
print("SUCCESS!")
print("Firestore test data:")
print(doc.get().to_dict())
