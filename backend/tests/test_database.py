import os
import pytest
from backend import database

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    # Override database path to use temporary test file
    original_db_path = database.DB_PATH
    original_db_dir = database.DB_DIR
    
    test_db = tmp_path / "test_hermes.db"
    database.DB_PATH = str(test_db)
    database.DB_DIR = str(tmp_path)
    
    database.init_db()
    
    yield
    
    # Restore original paths
    database.DB_PATH = original_db_path
    database.DB_DIR = original_db_dir

def test_database_init():
    assert os.path.exists(database.DB_PATH)

def test_save_and_retrieve_message():
    session_id = "user_test_123"
    
    # Verify initially empty
    assert len(database.get_chat_history(session_id)) == 0
    
    # Save a user message
    database.save_message(session_id, "user", "Привет, Jarvis")
    # Save an assistant reply
    database.save_message(session_id, "assistant", "Здравствуйте, Сэр")
    
    # Retrieve history
    history = database.get_chat_history(session_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Привет, Jarvis"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Здравствуйте, Сэр"

def test_chronological_ordering():
    session_id = "user_order_999"
    
    database.save_message(session_id, "user", "Msg 1")
    database.save_message(session_id, "assistant", "Msg 2")
    database.save_message(session_id, "user", "Msg 3")
    
    history = database.get_chat_history(session_id, limit=2)
    # limit=2 should return the last two messages in chronological order (Msg 2, Msg 3)
    assert len(history) == 2
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "Msg 2"
    assert history[1]["role"] == "user"
    assert history[1]["content"] == "Msg 3"

def test_clear_chat_history():
    session_id = "user_clear_abc"
    
    database.save_message(session_id, "user", "Hello")
    assert len(database.get_chat_history(session_id)) == 1
    
    database.clear_chat_history(session_id)
    assert len(database.get_chat_history(session_id)) == 0

def test_session_metadata_titles():
    session_id = "chat_test_session_title"
    
    # Verify title is initially None
    assert database.get_session_title(session_id) is None
    
    # Save a custom title
    database.save_session_title(session_id, "Interesting Chat About AI")
    assert database.get_session_title(session_id) == "Interesting Chat About AI"
    
    # Update the title
    database.save_session_title(session_id, "Updated Chat Title")
    assert database.get_session_title(session_id) == "Updated Chat Title"
    
    # Delete the title
    assert database.delete_session_title(session_id) is True
    assert database.get_session_title(session_id) is None
    
    # Deleting again should return False (not found)
    assert database.delete_session_title(session_id) is False
