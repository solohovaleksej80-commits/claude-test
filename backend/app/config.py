from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    admin_ids: str = ""
    database_url: str = "sqlite:///./tradesim.db"
    start_balance: float = 1000.0
    dev_mode: bool = True
    jwt_secret: str = "dev-secret-change-me"
    webapp_url: str = "http://localhost:5500"

    @property
    def admin_id_set(self) -> set[int]:
        ids = set()
        for part in self.admin_ids.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids


settings = Settings()
