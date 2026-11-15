from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    dashscope_api_key: str = ""
    dashscope_base_url: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    data_dir: str = "../data"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve()


settings = Settings()
