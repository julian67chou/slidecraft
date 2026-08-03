"""DeckSpec 內嵌（Bento-style）單元測試。

執行：python tests/test_embed_spec.py  或  pytest tests/test_embed_spec.py
覆蓋：
- 完整 spec 內嵌（title + 全部 slides）
- shadowing 回歸：內嵌必須是完整 DeckSpec，不是最後一個 slide
- `</script>` escape：惡意內容不破壞 HTML，JSON 可完整還原
- embed_spec=False / spec=None 不內嵌
- 既有 inline_svg 不受內嵌影響
"""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from renderers.html.renderer import render_deck, _embed_spec_block


def _load_fixture():
    spec = json.loads((ROOT / "cross-culture-spec.json").read_text(encoding="utf-8"))
    tokens = yaml.safe_load((ROOT / "design-tokens/themes/tech-neon.yaml").read_text(encoding="utf-8"))
    return spec, tokens


def _extract_block(html):
    m = re.search(r'<script type="application/json" id="deck-spec">(.*?)</script>', html, re.S)
    assert m, "deck-spec block 不存在"
    raw = m.group(1).strip()
    return json.loads(raw.replace("\\u003c", "<"))


def test_embed_full_spec():
    """內嵌必須是完整 DeckSpec，不是最後一個 slide（shadowing 回歸）。"""
    spec, tokens = _load_fixture()
    html = render_deck(spec["slides"], tokens, title=spec.get("title"), spec=spec, embed_spec=True)
    embedded = _extract_block(html)
    assert embedded.get("title") == spec.get("title")
    assert len(embedded.get("slides", [])) == len(spec["slides"])


def test_script_tag_escape():
    """spec 內容含 </script> 時，raw HTML 內不該有未逸出 <，且 JSON 可完整還原。"""
    evil = {
        "title": "XSS",
        "slides": [{
            "id": "s1", "layout": "content",
            "content": {
                "title": "</script><script>alert(1)</script>",
                "bullets": ["<b>hi</b>", "a < b && c > d"],
            },
        }],
    }
    block = _embed_spec_block(evil)
    raw = re.search(r'<script type="application/json" id="deck-spec">(.*?)</script>', block, re.S).group(1)
    assert "<" not in raw, "JSON 內有未逸出 <"
    back = json.loads(raw.replace("\\u003c", "<"))
    assert back["slides"][0]["content"]["title"] == "</script><script>alert(1)</script>"
    assert back["slides"][0]["content"]["bullets"][1] == "a < b && c > d"


def test_embed_spec_disabled():
    spec, tokens = _load_fixture()
    html = render_deck(spec["slides"], tokens, title=spec.get("title"), spec=spec, embed_spec=False)
    assert "deck-spec" not in html


def test_spec_none():
    spec, tokens = _load_fixture()
    html = render_deck(spec["slides"], tokens, title=spec.get("title"), spec=None)
    assert "deck-spec" not in html


def test_inline_svg_not_broken():
    """既有 inline_svg（含 </svg>）不應受內嵌影響。"""
    spec, tokens = _load_fixture()
    html = render_deck(spec["slides"], tokens, title=spec.get("title"), spec=spec, embed_spec=True)
    assert html.count("</svg>") >= 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"✅ {t.__name__}")
    print(f"\n🎉 {len(tests)} 個測試全過")
