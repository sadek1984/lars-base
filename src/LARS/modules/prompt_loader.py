"""prompt_loader.py — Load prompt templates from the prompts/ directory.

Templates use $variable or ${variable} syntax (Python string.Template).
Literal dollar signs must be escaped as $$.
Curly braces { } in code examples are always treated as literals.
"""

from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, **kwargs) -> str:
    """Read prompts/<name>.md and substitute $variables with kwargs.

    Uses safe_substitute so missing keys are left as $variable rather than
    raising a KeyError — useful when the caller only fills a subset of slots.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    return Template(path.read_text(encoding="utf-8")).safe_substitute(**kwargs)
