import os
import shutil
from pathlib import Path


os.environ["DATABASE_URL"] = "sqlite:///./data/test_paravoca.db"
os.environ["CHROMA_PATH"] = "./data/test_chroma"
os.environ["EMBEDDING_PROVIDER"] = "legacy_hash"
os.environ["EMBEDDING_MODEL"] = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
os.environ["EMBEDDING_DEVICE"] = "cpu"
os.environ["EMBEDDING_BATCH_SIZE"] = "32"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["LLM_ENABLED"] = "false"
os.environ["TOURAPI_SERVICE_KEY"] = ""
os.environ["KTO_PHOTO_CONTEST_ENABLED"] = "false"
os.environ["KTO_WELLNESS_ENABLED"] = "false"
os.environ["KTO_PET_ENABLED"] = "false"
os.environ["KTO_DURUNUBI_ENABLED"] = "false"
os.environ["KTO_AUDIO_ENABLED"] = "false"
os.environ["KTO_ECO_ENABLED"] = "false"
os.environ["KTO_TOURISM_PHOTO_ENABLED"] = "false"
os.environ["KTO_BIGDATA_ENABLED"] = "false"
os.environ["KTO_CROWDING_ENABLED"] = "false"
os.environ["KTO_RELATED_PLACES_ENABLED"] = "false"
os.environ["KTO_REGIONAL_TOURISM_DEMAND_ENABLED"] = "false"
os.environ["ALLOW_MEDICAL_API"] = "false"
os.environ["OFFICIAL_WEB_SEARCH_ENABLED"] = "false"
os.environ["EVALUATION_REPORT_DIR"] = "reports/test_evaluations"

test_db = Path("data/test_paravoca.db")
test_chroma = Path("data/test_chroma")
if test_db.exists():
    test_db.unlink()
if test_chroma.exists():
    shutil.rmtree(test_chroma)
