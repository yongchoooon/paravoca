import os
import shutil
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
TEST_DATA_DIR = BACKEND_ROOT / "data"
test_db = TEST_DATA_DIR / "test_paravoca.db"
test_chroma = TEST_DATA_DIR / "test_chroma"
test_poster_assets = TEST_DATA_DIR / "test_poster_assets"
test_logs = TEST_DATA_DIR / "test_logs"

os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
os.environ["CHROMA_PATH"] = str(test_chroma)
os.environ["EMBEDDING_MODEL"] = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
os.environ["EMBEDDING_DEVICE"] = "cpu"
os.environ["EMBEDDING_BATCH_SIZE"] = "32"
os.environ["OPENAI_API_KEY"] = ""
os.environ["POSTER_ASSET_DIR"] = str(test_poster_assets)
os.environ["POSTER_USAGE_LOG_DIR"] = str(test_logs)
os.environ["POSTER_PROMPT_LOG_DIR"] = str(test_logs / "poster_prompts")
os.environ["GEMINI_API_KEY"] = ""
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
os.environ["USD_KRW_RATE"] = "1490"

if test_db.exists():
    test_db.unlink()
if test_chroma.exists():
    shutil.rmtree(test_chroma)
if test_poster_assets.exists():
    shutil.rmtree(test_poster_assets)
if test_logs.exists():
    shutil.rmtree(test_logs)


class TestSemanticEmbeddingProvider:
    name = "local"
    model = "test-semantic-embedding"
    dimension = 8

    def _embed(self, text: str) -> list[float]:
        tokens = [token for token in str(text).lower().replace("\n", " ").split(" ") if token]
        vector = [0.0] * self.dimension
        for token in tokens or ["empty"]:
            index = sum(ord(char) for char in token) % self.dimension
            vector[index] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.fixture(autouse=True)
def use_test_semantic_embedding_provider(monkeypatch):
    provider = TestSemanticEmbeddingProvider()
    monkeypatch.setattr("app.rag.chroma_store.get_embedding_provider", lambda: provider)
