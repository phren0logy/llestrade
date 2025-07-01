#!/usr/bin/env python
"""
Test that both app_config versions work the same way.
"""

import os
import sys

# Suppress logging noise during tests
import logging
logging.getLogger().setLevel(logging.WARNING)

# Test current app_config
print("Testing current app_config with compatibility module...")
import app_config as current_config

providers = current_config.get_available_providers_and_models()
print(f"Available providers: {len(providers)}")
for p in providers:
    print(f"  - {p['display_name']}")

# Test migrated app_config
print("\nTesting migrated app_config with direct llm package...")
import app_config_migrated as migrated_config

migrated_providers = migrated_config.get_available_providers_and_models()
print(f"Available providers: {len(migrated_providers)}")
for p in migrated_providers:
    print(f"  - {p['display_name']}")

# Compare results
assert len(providers) == len(migrated_providers), "Provider counts differ"
assert providers == migrated_providers, "Provider lists differ"

print("\n✅ Both versions produce identical results!")

# Test the factory functions (will fail without API keys, but that's expected)
print("\nTesting factory functions...")

# Temporarily set to use Gemini which we know works
current_settings = current_config.load_app_settings()
current_settings["selected_llm_provider_id"] = "gemini"
current_config.save_app_settings(current_settings)

# Test current version
current_result = current_config.get_configured_llm_client()
if current_result:
    print(f"Current version: Got {current_result['provider_label']} client")
    # The new provider has 'generate' method, not 'generate_response'
    assert hasattr(current_result['client'], 'generate'), "Missing generate method"

# Test migrated version
migrated_result = migrated_config.get_configured_llm_provider()
if migrated_result:
    print(f"Migrated version: Got {migrated_result['provider_label']} provider")
    assert hasattr(migrated_result['provider'], 'generate'), "Missing generate method"

# Test backward compatibility alias
compat_result = migrated_config.get_configured_llm_client()
assert compat_result is not None, "Backward compatibility alias not working"
assert compat_result['provider_id'] == migrated_result['provider_id'], "Provider IDs don't match"

print("\n✅ All tests passed!")