from dataclasses import dataclass


@dataclass
class EngineConfig:
    fetch_interval_sec: int = 300     # 5 min
    ticker_interval_sec: int = 8      # bytt sak hvert 8s
    rotation_seconds: int = 60
    min_score: float = 2.5
    max_items: int = 50
