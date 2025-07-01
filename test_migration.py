#!/usr/bin/env python
"""
Test script to verify migration from compatibility module to direct llm package usage.
"""

import logging
import sys

# Test current compatibility module
print("Testing compatibility module...")
try:
    from llm_utils_compat import LLMClientFactory, BaseLLMClient
    client = LLMClientFactory.create_client(provider="auto")
    print(f"✓ Compatibility module works - client type: {type(client).__name__}")
except Exception as e:
    print(f"✗ Compatibility module failed: {e}")
    sys.exit(1)

# Test new direct usage
print("\nTesting direct llm package usage...")
try:
    from llm.factory import create_provider
    from llm.base import BaseLLMProvider
    provider = create_provider("auto")
    print(f"✓ Direct llm package works - provider type: {type(provider).__name__}")
    
    # Test that the provider has the expected interface
    assert hasattr(provider, 'generate'), "Provider missing generate method"
    assert hasattr(provider, 'count_tokens'), "Provider missing count_tokens method"
    assert hasattr(provider, 'initialized'), "Provider missing initialized property"
    print("✓ Provider has expected interface")
    
except Exception as e:
    print(f"✗ Direct llm package failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ Migration test passed - both approaches work!")