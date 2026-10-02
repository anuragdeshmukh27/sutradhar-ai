from pathlib import Path

_DIR = Path(__file__).parent


def load(name: str, **vars) -> str:
    """Load prompts/<name>.md and substitute {{var}} placeholders."""
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text
