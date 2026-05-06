import os
import shutil
from pathlib import Path


os.environ["DATABASE_URL"] = "sqlite:///./data/test_travelops.db"
os.environ["CHROMA_PATH"] = "./data/test_chroma"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["LLM_ENABLED"] = "false"

test_db = Path("data/test_travelops.db")
test_chroma = Path("data/test_chroma")
if test_db.exists():
    test_db.unlink()
if test_chroma.exists():
    shutil.rmtree(test_chroma)
