import os
from google.cloud import storage
from dotenv import dotenv_values

cfg = dotenv_values(".env")
BUCKET = cfg.get("GCS_BUCKET", "euna-studio.appspot.com")
DB1 = cfg.get("GCS_DB1_PATH", "ios-db/medical_fts.sqlite")
DB2 = cfg.get("GCS_DB2_PATH", "ios-db/output.db")
DATA_DIR = cfg.get("DATA_DIR", "./data")

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR

def files_status():
    ensure_data_dir()
    paths = [("medical_fts.sqlite", DB1), ("output.db", DB2)]
    ret = []
    for local, remote in paths:
        p = os.path.join(DATA_DIR, local)
        ret.append({
            "local": p,
            "present": os.path.exists(p),
            "remote": f"gs://{BUCKET}/{remote}"
        })
    return ret

def download_all(google_credentials_json: str | None = None):
    """
    Descarga los .sqlite desde GCS.
    Requiere GOOGLE_APPLICATION_CREDENTIALS en el entorno o pasar ruta JSON.
    """
    ensure_data_dir()
    if google_credentials_json:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_credentials_json

    client = storage.Client()
    bucket = client.bucket(BUCKET)

    targets = [(DB1, "medical_fts.sqlite"), (DB2, "output.db")]
    for remote, local in targets:
        blob = bucket.blob(remote)
        dst = os.path.join(DATA_DIR, local)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        blob.download_to_filename(dst)
    return files_status()
