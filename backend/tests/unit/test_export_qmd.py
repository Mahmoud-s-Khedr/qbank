from qbank.export.qmd import render_qmd

TWO = 2


def assets(known: dict[str, str]):  # type: ignore[no-untyped-def]  # tiny test helper
    return known.get


def test_inline_and_display_math_use_katex_spans() -> None:
    html = render_qmd("قيمة $x^2$ ثم\n\n$$\\frac{a}{b}$$")
    assert '<span class="math inline">\\(x^2\\)</span>' in html
    assert '<div class="math display">\\[\\frac{a}{b}\\]</div>' in html


def test_math_is_escaped() -> None:
    assert "&lt;" in render_qmd("$a<b$")


def test_raw_html_is_never_passed_through() -> None:
    html = render_qmd('<script>alert(1)</script> <b onclick="x()">hi</b>\n\n<div>block</div>')
    assert "<script" not in html
    assert "<b " not in html
    assert "<div>" not in html
    assert "&lt;script&gt;" in html


def test_asset_images_are_inlined_as_data_uris() -> None:
    uri = "data:image/png;base64,AAAA"
    html = render_qmd("![شكل](asset:abc)", assets({"abc": uri}))
    assert f'<img src="{uri}" alt="شكل">' in html


def test_unknown_assets_and_external_images_become_placeholders() -> None:
    html = render_qmd("![a](asset:nope) ![b](https://example.com/x.png)", assets({}))
    assert "<img" not in html
    assert html.count("missing-asset") == TWO
    assert "example.com" not in html


def test_blanks_inline_and_on_their_own_line() -> None:
    html = render_qmd("املأ ____ الفراغ\n\n____\n\n___")
    assert html.count('<span class="blank"></span>') == TWO
    assert "<hr>" in html  # three underscores stay a rule, like the frontend


def test_blocks_carry_dir_auto() -> None:
    html = render_qmd("para\n\n- item\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert '<p dir="auto">' in html
    assert '<ul dir="auto">' in html
    assert '<li dir="auto">' in html
    assert '<table dir="auto">' in html
    assert '<td dir="auto">' in html


def test_inline_mode_has_no_paragraph() -> None:
    html = render_qmd("a ____ b", inline=True)
    assert "<p" not in html
    assert "blank" in html


def test_links_are_not_rendered_as_anchors_and_code_is_ltr() -> None:
    html = render_qmd("[x](javascript:alert(1)) [y](https://a.b)\n\n```\ncode <b>\n```")
    assert "<a " not in html
    assert '<pre dir="ltr"><code>code &lt;b&gt;' in html
