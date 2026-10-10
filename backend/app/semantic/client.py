from app.semantic.ollama import OllamaSemanticClient


def configured_semantic_client(settings):
    if settings.ai_execution_mode == "remote":
        from app.semantic.remote import RemoteSemanticClient
        return RemoteSemanticClient(settings.ollama_model, settings.ai_remote_wait_seconds)
    return OllamaSemanticClient(settings.ollama_base_url, settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds)
