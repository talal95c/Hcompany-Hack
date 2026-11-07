"""Compilation de transcriptions en leçons validées."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prep.compile.compiler import HoloCompiler

__all__ = ["HoloCompiler"]


def __getattr__(name: str) -> Any:
    if name == "HoloCompiler":
        from prep.compile.compiler import HoloCompiler

        return HoloCompiler
    raise AttributeError(name)
