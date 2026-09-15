"""설정 로드: config.yaml + 선택적 .env 자격증명."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

DEFAULT_BASE_URL = (
    "https://nowonsc.moonhwain.kr:447/rsvc/rsv_srm.html?b_id=nowonsc"
)

# 구역 안내 (비즈니스 규칙)
ZONE_INFO: dict[str, str] = {
    "H": "Healing (H1–H19)",
    "P": "Park (P1–P26)",
    "T": "Terrace (T1–T5)",
    "C": "Cabin (C1–C3) — 자격/이용 조건 확인 필요",
}


@dataclass
class Credentials:
    user_id: str | None = None
    password: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.user_id and self.password)


@dataclass
class AppConfig:
    base_url: str = DEFAULT_BASE_URL
    preferred_sites: list[str] = field(default_factory=lambda: ["P1", "P2", "P3", "H1", "H2"])
    nights: int = 1
    electricity: bool = True
    target_date: str | None = None
    headless: bool = False
    warm_login_seconds_before: int = 120
    stop_before_payment: bool = True
    timezone: str = "Asia/Seoul"
    artifacts_dir: str = "artifacts"
    credentials: Credentials = field(default_factory=Credentials)
    project_root: Path = field(default_factory=Path.cwd)

    def artifacts_path(self) -> Path:
        p = Path(self.artifacts_dir)
        if not p.is_absolute():
            p = self.project_root / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    def warn_cabin_sites(self) -> list[str]:
        """캐빈(C*) 선택 시 경고용 목록."""
        return [s for s in self.preferred_sites if s.upper().startswith("C")]


def _find_project_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "config.example.yaml").exists() or (p / "pyproject.toml").exists():
            if (p / "src" / "choansan").exists() or (p / "config.example.yaml").exists():
                return p
    return cur


def load_config(
    config_path: str | Path | None = None,
    env_path: str | Path | None = None,
) -> AppConfig:
    root = _find_project_root()
    load_dotenv(env_path or (root / ".env"))

    cfg_file = Path(config_path) if config_path else (root / "config.yaml")
    raw: dict[str, Any] = {}
    if cfg_file.exists():
        with cfg_file.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    elif (root / "config.example.yaml").exists():
        # 개발/최초 실행: example 사용 (자격증명은 .env 만)
        with (root / "config.example.yaml").open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    creds = Credentials(
        user_id=os.getenv("CHOANSAN_USER_ID") or os.getenv("CHOANSAN_ID"),
        password=os.getenv("CHOANSAN_PASSWORD") or os.getenv("CHOANSAN_PW"),
    )

    nights = int(raw.get("nights", 1))
    if nights < 1 or nights > 2:
        raise ValueError("nights 는 1 또는 2 만 허용됩니다 (계정당 최대 2박).")

    return AppConfig(
        base_url=str(raw.get("base_url") or DEFAULT_BASE_URL),
        preferred_sites=list(raw.get("preferred_sites") or ["P1", "P2", "P3", "H1", "H2"]),
        nights=nights,
        electricity=bool(raw.get("electricity", True)),
        target_date=raw.get("target_date"),
        headless=bool(raw.get("headless", False)),
        warm_login_seconds_before=int(raw.get("warm_login_seconds_before", 120)),
        stop_before_payment=bool(raw.get("stop_before_payment", True)),
        timezone=str(raw.get("timezone") or "Asia/Seoul"),
        artifacts_dir=str(raw.get("artifacts_dir") or "artifacts"),
        credentials=creds,
        project_root=root,
    )
