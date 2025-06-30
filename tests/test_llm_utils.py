from llm_utils_compat import cached_count_tokens


def test_cached_count_tokens():
    # Mock class
    class MockClient:
        def count_tokens(self, text=None, messages=None):
            return {"success": True, "token_count": len(text or "") // 4}
    
    client = MockClient()
    
    # Test caching works
    result1 = cached_count_tokens(client, text="test text")
    result2 = cached_count_tokens(client, text="test text")
    
    # Should get same result and hit cache the second time
    assert result1 == result2
    
    # Different text should return different result (using longer text to ensure different token count)
    result3 = cached_count_tokens(client, text="this is a much longer different text string")
    assert result1 != result3

