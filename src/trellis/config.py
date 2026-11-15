import os
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.1.0"
USER_AGENT = f"Trellis/{VERSION} (personal non-commercial; https://github.com/zebede1980/Trellis)"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    secret_key: str
    secure_cookies: bool
    web_dir: Path
    nanogpt_api_key: str
    nanogpt_base_url: str
    tag_model: str
    rec_model: str
    lookup_model: str
    rec_web_search: bool
    rec_runs_per_day: int
    brave_api_key: str
    tmdb_token: str
    igdb_client_id: str
    igdb_client_secret: str
    start_worker: bool

    @property
    def db_path(self) -> Path:
        return self.data_dir / "trellis.db"


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def load() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("TRELLIS_DATA_DIR", "data")).resolve(),
        secret_key=os.environ.get("TRELLIS_SECRET_KEY", "dev-only-change-me"),
        secure_cookies=_flag("TRELLIS_SECURE_COOKIES"),
        web_dir=Path(os.environ.get("TRELLIS_WEB_DIR", Path(__file__).resolve().parents[2] / "web" / "build")),
        nanogpt_api_key=os.environ.get("NANOGPT_API_KEY", ""),
        nanogpt_base_url=os.environ.get("NANOGPT_BASE_URL", "https://nano-gpt.com/api/v1"),
        tag_model=os.environ.get("TAG_MODEL", "anthropic/claude-haiku-5.5"),
        rec_model=os.environ.get("REC_MODEL", "anthropic/claude-sonnet-5.5"),
        lookup_model=os.environ.get("LOOKUP_MODEL", "anthropic/claude-haiku-5.5"),
        rec_web_search=_flag("REC_WEB_SEARCH"),
        rec_runs_per_day=int(os.environ.get("REC_RUNS_PER_DAY", "10")),
        brave_api_key=os.environ.get("BRAVE_SEARCH_API_KEY", ""),
        tmdb_token=os.environ.get("TMDB_READ_TOKEN", ""),
        igdb_client_id=os.environ.get("IGDB_CLIENT_ID", ""),
        igdb_client_secret=os.environ.get("IGDB_CLIENT_SECRET", ""),
        start_worker=_flag("TRELLIS_WORKER", "1"),
    )
