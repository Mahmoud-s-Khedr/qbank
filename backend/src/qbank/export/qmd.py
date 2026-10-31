"""QMD (Markdown + TeX math) to HTML, mirroring the frontend ``QmdRenderer``.

Raw HTML is never passed through. Math is emitted as ``\\(...\\)`` / ``\\[...\\]`` inside
``<span class="math inline">`` / ``<div class="math display">`` and typeset by KaTeX in the browser
at print time. ``asset:<id>`` images are inlined as data URIs so the page needs no network.
"""

import re
from collections.abc import Callable, Sequence
from html import escape
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererProtocol
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from mdit_py_plugins.dollarmath import dollarmath_plugin

AssetResolver = Callable[[str], str | None]
"""Maps an asset id to a ``data:`` URI, or ``None`` when the asset is unknown."""

BLANK = re.compile(r"(_{4,})")
FULL_BLANK = re.compile(r"_{4,}")
BLOCKS_WITH_DIR = frozenset(
    {
        "paragraph_open",
        "heading_open",
        "bullet_list_open",
        "ordered_list_open",
        "list_item_open",
        "blockquote_open",
        "table_open",
        "th_open",
        "td_open",
    }
)
BLANK_HTML = '<span class="blank"></span>'
MISSING_FIGURE = "[figure]"


def _tex(token: Token) -> str:
    return escape(token.content.strip(), quote=False)


def _asset_of(env: EnvType) -> AssetResolver | None:
    resolver = env.get("assets")
    return resolver if callable(resolver) else None


def _math_inline(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return f'<span class="math inline">\\({_tex(tokens[idx])}\\)</span>'


def _math_double(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    # remark-math renders `$$..$$` inside a paragraph as display math.
    return f'<span class="math display-inline">\\[{_tex(tokens[idx])}\\]</span>'


def _math_block(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return f'<div class="math display">\\[{_tex(tokens[idx])}\\]</div>\n'


def _text(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    parts = BLANK.split(tokens[idx].content)
    return "".join(BLANK_HTML if FULL_BLANK.fullmatch(p) else escape(p) for p in parts)


def _hr(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    lines = env.get("lines")
    source_map = tokens[idx].map
    start = source_map[0] if source_map else None
    # The rule's own `markup` is not reliable for its length, so read the source line itself.
    line = lines[start] if isinstance(lines, list) and start is not None else ""
    if FULL_BLANK.fullmatch(line.strip()):
        return f'<p dir="auto">{BLANK_HTML}</p>\n'
    return "<hr>\n"


def _fence(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return f'<pre dir="ltr"><code>{escape(tokens[idx].content)}</code></pre>\n'


def _image(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    token = tokens[idx]
    src = str(token.attrGet("src") or "")
    alt = escape(token.content)
    resolver = _asset_of(env)
    uri = (
        resolver(src.removeprefix("asset:").strip())
        if resolver and src.startswith("asset:")
        else None
    )
    if uri is None:
        # External URLs are not fetched: exports must not depend on the network.
        return f'<span class="missing-asset" role="img" aria-label="{alt}">{MISSING_FIGURE}</span>'
    return f'<img src="{escape(uri)}" alt="{alt}">'


def _link_open(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return "<span>"


def _link_close(
    self: RendererProtocol, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return "</span>"


def _build() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "breaks": False}).enable(
        ["table", "strikethrough"]
    )
    dollarmath_plugin(md, allow_space=True, allow_digits=True, double_inline=True)
    for name, rule in (
        ("math_inline", _math_inline),
        ("math_inline_double", _math_double),
        ("math_block", _math_block),
        ("text", _text),
        ("hr", _hr),
        ("fence", _fence),
        ("code_block", _fence),
        ("image", _image),
        ("link_open", _link_open),
        ("link_close", _link_close),
    ):
        md.add_render_rule(name, rule)

    def add_dir(state: Any) -> None:
        for token in state.tokens:
            if token.type in BLOCKS_WITH_DIR:
                token.attrSet("dir", "auto")

    md.core.ruler.push("qmd_dir", add_dir)
    return md


_MD = _build()


def render_qmd(source: str, assets: AssetResolver | None = None, *, inline: bool = False) -> str:
    """HTML for one QMD string. ``inline`` renders without a wrapping paragraph."""
    env: dict[str, object] = {"assets": assets, "lines": source.splitlines()}
    if inline:
        return str(_MD.renderInline(source, env))
    return str(_MD.render(source, env))
