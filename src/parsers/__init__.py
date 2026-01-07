"""Bank statement parser registry with auto-discovery."""

import importlib
import pkgutil
from pathlib import Path
from typing import Type

from .base import BaseBankParser, StatementData, Transaction

# Registry of all available parsers
_parsers: dict[str, Type[BaseBankParser]] = {}


def register_parser(parser_class: Type[BaseBankParser]) -> Type[BaseBankParser]:
    """Decorator to register a parser class."""
    _parsers[parser_class.bank_name()] = parser_class
    return parser_class


def get_parser(bank_name: str) -> BaseBankParser:
    """Get a parser instance for the specified bank.

    Args:
        bank_name: The bank identifier (e.g., 'fnb')

    Returns:
        An instance of the appropriate parser

    Raises:
        ValueError: If no parser exists for the specified bank
    """
    if bank_name not in _parsers:
        available = ", ".join(_parsers.keys()) or "none"
        raise ValueError(
            f"No parser available for bank '{bank_name}'. "
            f"Available parsers: {available}"
        )
    return _parsers[bank_name]()


def list_available_parsers() -> list[str]:
    """List all available bank parsers."""
    return list(_parsers.keys())


def _discover_parsers() -> None:
    """Auto-discover and import all parser modules in this package."""
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name not in ("base", "__init__"):
            importlib.import_module(f".{module_info.name}", __package__)


# Auto-discover parsers on import
_discover_parsers()

__all__ = [
    "BaseBankParser",
    "StatementData",
    "Transaction",
    "get_parser",
    "list_available_parsers",
    "register_parser",
]
