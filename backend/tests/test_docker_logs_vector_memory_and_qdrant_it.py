import pytest
import uuid
from backend.rag import raw_index_vector, raw_search_vector, get_qdrant_client
from backend.memory import QdrantMemoryEngine

TEST_COLLECTION = "test_qdrant_it_collection"

@pytest.fixture(autouse=True)
def setup_teardown_collection():
    client = get_qdrant_client()
    try:
        from qdrant_client.http import models
        # Ensure clean collection
        client.recreate_collection(
            collection_name=TEST_COLLECTION,
            vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE)
        )
    except Exception as e:
        pytest.skip(f"Qdrant not available: {e}")
    yield
    try:
        client.delete_collection(collection_name=TEST_COLLECTION)
    except Exception:
        pass


def test_index_vector_with_numeric_string_id():
    """Test that indexing with a numeric string ID (which previously triggered Qdrant 400) succeeds."""
    trade_id = "test_trade_123"
    numeric_str_id = str(abs(hash(trade_id)) % (10**10))
    vector = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    payload = {"trade_id": trade_id, "pnl": 150.0, "status": "CLOSED"}

    success = raw_index_vector(
        doc_id=numeric_str_id,
        vector=vector,
        payload=payload,
        collection_name=TEST_COLLECTION
    )
    assert success is True

    # Verify search finds the payload
    results = raw_search_vector(vector=vector, limit=1, collection_name=TEST_COLLECTION)
    assert len(results) == 1
    assert results[0]["trade_id"] == trade_id
    assert results[0]["pnl"] == 150.0


def test_index_vector_with_arbitrary_string_id():
    """Test that indexing with an arbitrary non-UUID string ID succeeds."""
    doc_id = "trade_session_london_btc_long_entry"
    vector = [0.2, 0.1, 0.4, 0.3, 0.6, 0.5, 0.8, 0.7]
    payload = {"session": "london", "symbol": "BTC-USD"}

    success = raw_index_vector(
        doc_id=doc_id,
        vector=vector,
        payload=payload,
        collection_name=TEST_COLLECTION
    )
    assert success is True

    results = raw_search_vector(vector=vector, limit=1, collection_name=TEST_COLLECTION)
    assert len(results) == 1
    assert results[0]["symbol"] == "BTC-USD"


def test_index_vector_with_uuid_and_integer_ids():
    """Test that standard UUID and integer IDs continue to work properly."""
    # Integer ID
    int_id = 987654321
    vector1 = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
    res1 = raw_index_vector(doc_id=int_id, vector=vector1, payload={"kind": "int_id"}, collection_name=TEST_COLLECTION)
    assert res1 is True

    # UUID ID
    uuid_id = str(uuid.uuid4())
    vector2 = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    res2 = raw_index_vector(doc_id=uuid_id, vector=vector2, payload={"kind": "uuid_id"}, collection_name=TEST_COLLECTION)
    assert res2 is True

    # QdrantMemoryEngine interface delegation
    engine = QdrantMemoryEngine()
    res3 = engine.index_vector(doc_id="engine_str_id", vector=vector1, payload={"kind": "engine"}, collection_name=TEST_COLLECTION)
    assert res3 is True

    search_res = engine.search_vector(vector=vector1, limit=5, collection_name=TEST_COLLECTION)
    assert len(search_res) >= 2
