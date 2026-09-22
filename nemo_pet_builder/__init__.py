"""Repository-owned build tools for the Nemo Dango Codex pet."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nemo-dango-pet-builder")
except PackageNotFoundError:
    __version__ = "0+unknown"
