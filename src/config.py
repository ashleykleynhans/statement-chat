"""Configuration loader for the bank statement chat bot."""

from pathlib import Path
import yaml


def load_config(config_path: str | Path = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config


def get_config() -> dict:
    """Get configuration, searching in common locations."""
    search_paths = [
        Path("config.yaml"),
        Path(__file__).parent.parent / "config.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return load_config(path)

    raise FileNotFoundError("Could not find config.yaml in any expected location")  # pragma: no cover
