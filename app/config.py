from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.prompts import BRAND_RENDERING_DEFAULT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    llm_provider: str = 'xai'
    llm_api_key: str = ''
    xai_api_key: str = ''
    openai_api_key: str = ''
    llm_base_url: str = ''
    llm_model: str = ''
    llm_strict: bool = False
    llm_debug: bool = True

    image_api_key: str = ''
    image_base_url: str = 'https://api.openai.com/v1'
    image_model: str = 'gpt-image-1'

    output_dir: str = 'output'
    upload_dir: str = 'uploads'
    app_host: str = '127.0.0.1'
    app_port: int = 8000
    brand_name: str = 'TheoEngage Inc.'
    brand_logo_variant: str = 'globe_cross_no_shadow'
    brand_logo_languages: str = 'english_arabic'
    canva_only_images: bool = True
    session_secret: str = 'change-me-in-production'
    session_idle_timeout_seconds: int = 3600
    auth_db_path: str = 'output/auth/users.db'
    admin_username: str = 'admin'
    admin_password: str = 'admin12345'
    default_style_prompt: str = BRAND_RENDERING_DEFAULT

    def normalized_llm_provider(self) -> str:
        provider = (self.llm_provider or '').strip().lower()
        if provider in {'xai', 'openai'}:
            return provider
        return 'xai'

    def resolved_llm_api_key(self, provider: str | None = None) -> str:
        target = (provider or self.normalized_llm_provider()).strip().lower()
        if target == 'xai':
            return (self.xai_api_key or self.llm_api_key).strip()
        if target == 'openai':
            return (self.openai_api_key or self.llm_api_key).strip()
        return (self.llm_api_key or self.xai_api_key or self.openai_api_key).strip()

    def resolved_llm_base_url(self, provider: str | None = None) -> str:
        if self.llm_base_url.strip():
            return self.llm_base_url.strip()
        target = (provider or self.normalized_llm_provider()).strip().lower()
        if target == 'xai':
            return 'https://api.x.ai/v1'
        return 'https://api.openai.com/v1'

    def resolved_llm_model(self, provider: str | None = None) -> str:
        if self.llm_model.strip():
            return self.llm_model.strip()
        target = (provider or self.normalized_llm_provider()).strip().lower()
        if target == 'xai':
            return 'grok-4-fast-reasoning'
        return 'gpt-4o-mini'

    def llm_debug_snapshot(self, provider: str | None = None) -> dict[str, object]:
        target = (provider or self.normalized_llm_provider()).strip().lower()
        key = self.resolved_llm_api_key(target)
        return {
            'provider': target,
            'base_url': self.resolved_llm_base_url(target),
            'model': self.resolved_llm_model(target),
            'api_key_present': bool(key),
        }


settings = Settings()
