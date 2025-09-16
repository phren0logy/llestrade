"""
Arize Phoenix observability configuration for LLM tracing and debugging.
Uses OpenInference standards for consistent instrumentation.
"""

import os
import logging
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import json

try:
    import phoenix as px
    from phoenix.otel import register
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from openinference.instrumentation import using_attributes
    PHOENIX_AVAILABLE = True
except ImportError:
    PHOENIX_AVAILABLE = False
    px = None
    register = None
    trace = None
    Status = None
    StatusCode = None
    using_attributes = None


class PhoenixObservability:
    """
    Manages Arize Phoenix observability for the application.
    Provides tracing, debugging, and fixture generation capabilities.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.enabled = False
        self.client = None
        self.tracer = None
        self.project_name = "forensic-report-drafter"
        self.export_fixtures = False
        self.fixtures_dir = Path("tests/test_new/fixtures")
        
    def initialize(self, settings: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """
        Initialize Phoenix with configuration from settings or environment.
        
        Args:
            settings: Optional dict with Phoenix configuration
            
        Returns:
            Phoenix client if initialized, None otherwise
        """
        if not PHOENIX_AVAILABLE:
            self.logger.warning("Phoenix not available. Install with: pip install arize-phoenix")
            return None
            
        # Get configuration from settings or environment
        if settings:
            phoenix_settings = settings.get("phoenix_settings", {})
            self.enabled = phoenix_settings.get("enabled", False)
            port = phoenix_settings.get("port", 6006)
            self.project_name = phoenix_settings.get("project", "forensic-report-drafter")
            self.export_fixtures = phoenix_settings.get("export_fixtures", False)
        else:
            self.enabled = os.getenv("PHOENIX_ENABLED", "false").lower() == "true"
            port = int(os.getenv("PHOENIX_PORT", "6006"))
            self.project_name = os.getenv("PHOENIX_PROJECT", "forensic-report-drafter")
            self.export_fixtures = os.getenv("PHOENIX_EXPORT_FIXTURES", "false").lower() == "true"
        
        if not self.enabled:
            self.logger.info("Phoenix observability disabled")
            return None
        
        # Check if Phoenix is already running on the port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        phoenix_already_running = (result == 0)
            
        try:
            if phoenix_already_running:
                self.logger.info(f"Phoenix already running on port {port}, connecting to existing server")
            else:
                # Launch Phoenix locally in development mode
                self.logger.info(f"Launching new Phoenix server on port {port}")
                # Set environment variables for Phoenix (to avoid deprecated parameters)
                os.environ["PHOENIX_PORT"] = str(port)
                os.environ["PHOENIX_HOST"] = "127.0.0.1"
                px.launch_app()
            
            # Register project for organized traces
            tracer_provider = register(
                project_name=self.project_name,
                endpoint=f"http://localhost:{port}/v1/traces"
            )
            
            # Get tracer for manual instrumentation
            self.tracer = trace.get_tracer(__name__)
            
            # Get Phoenix client
            self.client = px.Client()
            
            self.logger.info(f"Phoenix initialized: http://localhost:{port}")
            self.logger.info(f"Project: {self.project_name}")
            
            # Create fixtures directory if export is enabled
            if self.export_fixtures:
                self.fixtures_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Export fixtures enabled: {self.fixtures_dir}")
            
            return self.client
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Phoenix: {e}")
            self.enabled = False
            return None
    
    @contextmanager
    def trace_operation(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Context manager for tracing operations with Phoenix.
        
        Args:
            name: Operation name for the span
            attributes: Optional attributes to attach to the span
        """
        if not self.enabled or not self.tracer:
            yield None
            return
            
        with self.tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value) if value is not None else "")
            
            try:
                yield span
            except Exception as e:
                if span:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
    
    def trace_llm_call(self, model_name: Optional[str] = None):
        """
        Decorator for tracing LLM calls with OpenInference semantic conventions.
        
        Args:
            model_name: Optional model name to override runtime detection
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self.enabled:
                    return func(*args, **kwargs)
                
                # Extract model from kwargs or use provided
                runtime_model = kwargs.get("model", model_name or "unknown")
                
                # Build attributes using OpenInference conventions
                attributes = {
                    "openinference.span.kind": "LLM",
                    "llm.model_name": runtime_model,
                    "llm.provider": self._detect_provider(func.__module__),
                }
                
                # Add input prompt if available
                if "prompt" in kwargs:
                    attributes["llm.input_messages"] = str(kwargs["prompt"])[:1000]
                
                # Add temperature if specified
                if "temperature" in kwargs:
                    attributes["llm.temperature"] = kwargs["temperature"]
                
                with self.trace_operation(f"llm.{func.__name__}", attributes) as span:
                    try:
                        result = func(*args, **kwargs)
                        
                        # Record output
                        if span and result:
                            if isinstance(result, str):
                                span.set_attribute("llm.output_messages", result[:1000])
                            elif hasattr(result, "content"):
                                span.set_attribute("llm.output_messages", str(result.content)[:1000])
                            
                            # Extract token counts if available
                            if hasattr(result, "usage"):
                                span.set_attribute("llm.token_count.prompt", result.usage.input_tokens)
                                span.set_attribute("llm.token_count.completion", result.usage.output_tokens)
                                span.set_attribute("llm.token_count.total", result.usage.total_tokens)
                        
                        # Export fixture if enabled
                        if self.export_fixtures and result:
                            self._save_fixture(runtime_model, kwargs, result)
                        
                        return result
                        
                    except Exception as e:
                        self.logger.error(f"LLM call failed: {e}")
                        raise
                        
            return wrapper
        return decorator
    
    def _detect_provider(self, module_name: str) -> str:
        """Detect LLM provider from module name."""
        if "anthropic" in module_name.lower():
            return "anthropic"
        elif "openai" in module_name.lower():
            return "openai"
        elif "gemini" in module_name.lower() or "google" in module_name.lower():
            return "google"
        return "unknown"
    
    def _save_fixture(self, model: str, inputs: Dict, output: Any):
        """
        Save LLM response as test fixture for mocking.
        
        Args:
            model: Model name used
            inputs: Input parameters
            output: LLM response
        """
        if not self.export_fixtures:
            return
            
        try:
            # Create fixture filename
            import hashlib
            import time
            
            # Hash the prompt for uniqueness
            prompt_hash = hashlib.md5(
                str(inputs.get("prompt", ""))[:500].encode()
            ).hexdigest()[:8]
            
            timestamp = int(time.time())
            filename = f"{model}_{prompt_hash}_{timestamp}.json"
            filepath = self.fixtures_dir / filename
            
            # Prepare fixture data
            fixture = {
                "model": model,
                "input": {
                    "prompt": inputs.get("prompt", "")[:1000],
                    "temperature": inputs.get("temperature"),
                    "max_tokens": inputs.get("max_tokens"),
                },
                "output": {
                    "content": str(output)[:5000] if output else None,
                    "usage": {}
                }
            }
            
            # Add usage if available
            if hasattr(output, "usage"):
                fixture["output"]["usage"] = {
                    "input_tokens": getattr(output.usage, "input_tokens", 0),
                    "output_tokens": getattr(output.usage, "output_tokens", 0),
                    "total_tokens": getattr(output.usage, "total_tokens", 0),
                }
            
            # Save fixture
            with open(filepath, "w") as f:
                json.dump(fixture, f, indent=2)
            
            self.logger.debug(f"Saved fixture: {filename}")
            
        except Exception as e:
            self.logger.warning(f"Failed to save fixture: {e}")
    
    def get_traces(self) -> Optional[list]:
        """
        Retrieve traces from Phoenix for analysis or export.
        
        Returns:
            List of traces if available, None otherwise
        """
        if not self.client:
            return None
            
        try:
            # Note: This is a placeholder - actual implementation depends on Phoenix client API
            # You would typically query traces by project and time range
            return []  # Phoenix client API to get traces
        except Exception as e:
            self.logger.error(f"Failed to get traces: {e}")
            return None
    
    def shutdown(self):
        """Shutdown Phoenix gracefully."""
        if self.client:
            try:
                self.logger.info("Shutting down Phoenix")
                # Phoenix shutdown if needed
            except Exception as e:
                self.logger.warning(f"Error during Phoenix shutdown: {e}")


# Global instance for easy access
phoenix = PhoenixObservability()


def setup_observability(settings: Optional[Dict[str, Any]] = None):
    """
    Initialize Phoenix observability for the application.
    
    Args:
        settings: Optional settings dict with Phoenix configuration
        
    Returns:
        Phoenix client if successful, None otherwise
    """
    return phoenix.initialize(settings)


def trace_llm_call(model_name: Optional[str] = None):
    """
    Decorator for tracing LLM calls.
    
    Args:
        model_name: Optional model name to use
    """
    return phoenix.trace_llm_call(model_name)


@contextmanager
def trace_operation(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Context manager for tracing operations.
    
    Args:
        name: Operation name
        attributes: Optional attributes to attach
    """
    with phoenix.trace_operation(name, attributes) as span:
        yield span