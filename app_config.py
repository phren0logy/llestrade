import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Assuming llm_utils.py is in the same directory or accessible in PYTHONPATH
from llm_utils import BaseLLMClient, LLMClientFactory

SETTINGS_FILE = "app_settings.json"
DEFAULT_SETTINGS = {
    "selected_llm_provider_id": "anthropic",
    "llm_provider_configs": {
        "anthropic": {
            "enabled": True,
            "label": "Anthropic Claude",
            "default_model": "claude-sonnet-4-20250514"
        },
        "gemini": {
            "enabled": True,
            "label": "Google Gemini",
            "default_model": "gemini-2.5-pro-preview-05-06"
        },
        "azure_openai": {
            "enabled": True,
            "label": "Azure OpenAI",
            "default_deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),  # Read from environment
            "azure_endpoint": None,
            "api_version": None
        }
    },
    "general_settings": {
        "debug_mode": False,
        "default_system_prompt": "You are a helpful AI assistant."
    }
}

def get_available_providers_and_models() -> list[dict[str, str]]:
    """
    Loads app settings and returns a list of available (enabled) LLM providers
    and their default models.

    Returns:
        A list of dictionaries, where each dictionary contains:
        'id': provider_id (e.g., "anthropic")
        'label': provider_label (e.g., "Anthropic Claude")
        'model': default_model_name or deployment_id
        'display_name': A user-friendly string like "Anthropic Claude (claude-3-sonnet-latest)"
    """
    settings = load_app_settings()
    providers_and_models = []
    provider_configs = settings.get("llm_provider_configs", {})

    for provider_id, config in provider_configs.items():
        if config.get("enabled", False):
            label = config.get("label", provider_id)
            model = None
            if provider_id == "azure_openai":
                model = config.get("default_deployment_name")
            else:
                model = config.get("default_model")

            if model: # Only add if a model/deployment is specified
                display_name = f"{label} ({model})"
                providers_and_models.append({
                    "id": provider_id,
                    "label": label,
                    "model": model,
                    "display_name": display_name
                })
            else:
                logging.warning(f"Provider '{label}' (ID: {provider_id}) is enabled but has no default model/deployment configured. It will not be available for selection.")
    return providers_and_models

def load_app_settings() -> dict:
    """Loads application settings from SETTINGS_FILE, creates it with defaults if not found."""
    if not os.path.exists(SETTINGS_FILE):
        logging.info(f"'{SETTINGS_FILE}' not found. Creating with default settings.")
        save_app_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            
        # Override Azure deployment name from environment if available
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        if azure_deployment and "llm_provider_configs" in settings and "azure_openai" in settings["llm_provider_configs"]:
            settings["llm_provider_configs"]["azure_openai"]["default_deployment_name"] = azure_deployment
            logging.info(f"Using Azure OpenAI deployment name from environment: {azure_deployment}")
            
        return settings
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error loading '{SETTINGS_FILE}': {e}. Returning default settings.")
        return DEFAULT_SETTINGS.copy()

def save_app_settings(settings: dict):
    """Saves the provided settings dictionary to SETTINGS_FILE."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        logging.info(f"Settings saved to '{SETTINGS_FILE}'.")
    except IOError as e:
        logging.error(f"Error saving settings to '{SETTINGS_FILE}': {e}")

def get_configured_llm_client(
    provider_id_override: Optional[str] = None,
    model_override: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Attempts to initialize an LLM client.
    Uses the selected provider from app_settings.json by default.
    Can be overridden with specific provider_id and model.

    Args:
        provider_id_override: If provided, use this provider_id instead of the one in settings.
        model_override: If provided, use this model/deployment name.

    Returns:
        A dictionary with the client instance and its configuration if successful,
        None otherwise. Errors are logged.
    """
    settings = load_app_settings()

    selected_provider_id = provider_id_override if provider_id_override else settings.get("selected_llm_provider_id")

    if not selected_provider_id:
        logging.error(
            f"No LLM provider selected (either via override or in '{SETTINGS_FILE}'). "
            "Please configure one via the UI or ensure override is passed."
        )
        return None

    provider_configs = settings.get("llm_provider_configs", {})
    specific_config = provider_configs.get(selected_provider_id)

    if not specific_config:
        logging.error(
            f"Configuration for selected provider '{selected_provider_id}' not found "
            f"in '{SETTINGS_FILE}'."
        )
        return None

    if not specific_config.get("enabled", False):
        logging.error(
            f"Selected LLM provider '{selected_provider_id}' "
            f"(Label: '{specific_config.get('label', 'N/A')}') is disabled in settings."
        )
        return None

    general_cfg = settings.get("general_settings", {})
    provider_label = specific_config.get("label", selected_provider_id)

    factory_args = {
        "provider": selected_provider_id,
        "api_key": None,  # Clients in llm_utils.py will pick up from environment variables
        "default_system_prompt": general_cfg.get("default_system_prompt"),
        "debug": general_cfg.get("debug_mode", False),
        # Consider adding timeout, max_retries to general_settings or provider_configs if needed
    }

    effective_model_name = None
    if selected_provider_id == "azure_openai":
        factory_args["azure_endpoint"] = specific_config.get("azure_endpoint")
        factory_args["api_version"] = specific_config.get("api_version")
        effective_model_name = model_override if model_override else specific_config.get("default_deployment_name")
        if not effective_model_name:
            logging.error(
                f"Azure OpenAI is selected, but its 'default_deployment_name' is not configured "
                f"(either via override or in '{SETTINGS_FILE}' for provider '{provider_label}'). This is required."
            )
            return None
    else:  # For Anthropic, Gemini, etc.
        effective_model_name = model_override if model_override else specific_config.get("default_model")
        if not effective_model_name:
            logging.error(
                f"Provider '{provider_label}' is selected, but its 'default_model' "
                f"is not configured (either via override or in '{SETTINGS_FILE}')."
            )
            return None

    logging.info(f"Attempting to initialize LLM client: {provider_label} "
                 f"(ID: {selected_provider_id}) with model/deployment: '{effective_model_name}'")

    client: Optional[BaseLLMClient] = LLMClientFactory.create_client(**factory_args)

    if client and client.is_initialized:
        logging.info(f"Successfully initialized LLM client: {provider_label}")
        return {
            "client": client,
            "provider_id": selected_provider_id,
            "provider_label": provider_label,
            "effective_model_name": effective_model_name,
        }
    else:
        logging.error(
            f"Failed to initialize the selected LLM provider: {provider_label} (ID: {selected_provider_id}). "
            "Please check its API key in environment variables, any specific configurations "
            f"(like Azure deployment name: '{effective_model_name if selected_provider_id == 'azure_openai' else 'N/A'}') "
            "in settings, and network connectivity. The client's own logs may have more details."
        )
        return None

if __name__ == '__main__':
    # Basic example of how to use these functions
    # Setup basic logging for the example
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # --- Simulate UI interaction: User selects Azure OpenAI and configures it ---
    # current_settings = load_app_settings()
    # current_settings["selected_llm_provider_id"] = "azure_openai"
    # current_settings["llm_provider_configs"]["azure_openai"]["enabled"] = True
    # # IMPORTANT: The user would need to set their actual deployment name here or via a UI.
    # # For this example, if AZURE_OPENAI_DEPLOYMENT_NAME is in env, use it, else a placeholder.
    # azure_deployment_name_from_env = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_EXAMPLE_FOR_TESTING")
    # if azure_deployment_name_from_env:
    #     current_settings["llm_provider_configs"]["azure_openai"]["default_deployment_name"] = azure_deployment_name_from_env
    #     print(f"Using Azure deployment name from env for example: {azure_deployment_name_from_env}")
    # else:
    #     # This will cause get_configured_llm_client to fail if Azure is selected and this placeholder isn't replaced
    #     current_settings["llm_provider_configs"]["azure_openai"]["default_deployment_name"] = "YOUR_AZURE_DEPLOYMENT_NAME_HERE"
    #     print("Azure deployment name not in env for example, using placeholder. Client init will likely fail if Azure is selected.")
    # save_app_settings(current_settings)
    # print(f"Simulated selection: Azure OpenAI. Ensure '{SETTINGS_FILE}' reflects this and Azure env vars are set.")
    # print("Ensure AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, OPENAI_API_VERSION are set in your .env file.")
    # print("----------------------------------------------------")

    active_client_info = get_configured_llm_client()
    
    document_id_example = "DOC-EXAMPLE-001"

    if active_client_info:
        client_instance = active_client_info["client"]
        model_name_to_use = active_client_info["effective_model_name"]
        active_provider_label = active_client_info["provider_label"]

        print(f"Successfully obtained LLM client: {active_provider_label} "
              f"for document '{document_id_example}' using model/deployment: '{model_name_to_use}'")
        
        # Example: Using the client
        # Ensure your .env file is loaded if clients depend on it for API keys not passed directly.
        # (llm_utils.py BaseLLMClient and individual clients handle .env loading)
        # test_prompt = "What is the capital of France?"
        # response = client_instance.generate_response(prompt_text=test_prompt, model=model_name_to_use)

        # if response["success"]:
        #     print(f"Response from {active_provider_label}: {response['content']}")
        # else:
        #     print(f"API call failed for {active_provider_label}. Error: {response['error']}")
        #     logging.error(f"LLM API call failed for document {document_id_example} "
        #                   f"using provider {active_provider_label}. Error: {response['error']}. "
        #                   "Document needs to be re-run.")
    else:
        print(f"Failed to obtain an active LLM client for document '{document_id_example}'. "
              "Check logs for details. Document processing cannot proceed and will need to be re-run.")
        logging.error(
            f"Document processing failed for {document_id_example} because the configured LLM provider "
            "could not be initialized. Document needs to be re-run."
        ) 
