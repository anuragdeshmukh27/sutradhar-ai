"""Plug-in tool registry. Drop a new module in this folder that defines a Tool subclass
decorated with @register and it is auto-discovered; the planner prompt lists tools from the registry."""
import importlib
import pkgutil
from typing import ClassVar

REGISTRY: dict[str, "Tool"] = {}


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    args_schema: ClassVar[dict[str, str]]  # arg name -> description
    reversible: ClassVar[bool] = True

    def run(self, args: dict, ctx: dict) -> dict:
        """Return {"ok": bool, "summary": str (deterministic), "data": {...}, "undo_payload": {...}}."""
        raise NotImplementedError

    def undo(self, record: dict) -> dict:
        """record is the ledger row as a dict. Return {"ok": bool, "summary": str}."""
        raise NotImplementedError


def register(cls):
    REGISTRY[cls.name] = cls()
    return cls


def describe() -> str:
    lines = []
    for name in sorted(REGISTRY):
        t = REGISTRY[name]
        args = ", ".join(f"{k}: {v}" for k, v in t.args_schema.items())
        rev = "reversible" if t.reversible else "IRREVERSIBLE"
        lines.append(f"- {name} ({rev}): {t.description} Args: {{{args}}}")
    return "\n".join(lines)


for _m in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_m.name}")
