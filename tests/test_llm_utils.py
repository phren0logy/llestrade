import sys
from pathlib import Path

# Ensure we can import from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm import count_tokens_cached


def test_count_tokens_cached():
    # Mock class
    class MockProvider:
        def count_tokens(self, text=None, messages=None):
            return {"success": True, "token_count": len(text or "") // 4}
    
    provider = MockProvider()
    
    # Test caching works
    result1 = count_tokens_cached(provider, text="test text")
    result2 = count_tokens_cached(provider, text="test text")
    
    # Should get same result and hit cache the second time
    assert result1 == result2
    
    # Different text should return different result (using longer text to ensure different token count)
    result3 = count_tokens_cached(provider, text="this is a much longer different text string")
    assert result1 != result3

