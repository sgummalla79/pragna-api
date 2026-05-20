"""
Services layer — all business logic and domain orchestration.

Services sit between routes and repositories. Each service:
  - Owns one domain of business rules
  - Depends only on repositories (never on other services directly)
  - Is stateless — no instance-level mutable state
  - Receives the DBContext at construction time via dependency injection

Routes call services; services call repositories. Routes never call repositories.

Available services:
  PricingService       — LLM cost lookup, loaded from llm_models at startup
  UsageService         — record token usage with cost calculation
  ProviderService      — connect/disconnect LLM providers and their API keys
  LLMModelService      — manage per-user model activations and display names
  SkillService         — install/uninstall skills, manage draft/publish lifecycle
  ConversationService  — add skills to conversations, manage execution snapshots
  ExecutionService     — start, retry, and resume skill pipeline executions
"""
