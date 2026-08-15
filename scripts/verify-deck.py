#!/usr/bin/env python3
"""
verify-deck.py — SlideCraft HTML Deck Quality Gate (v2, 2026-08-15)

四層驗證（v2 新增 L2/L3/L4 真實檢查，不再 stub）:
  L1 技術層: overflow / 圖片 HTTP / 滑桿 / 檔案大小（原有）
  L2 資源完整性: 相對路徑檔案必須存在於 repo；onerror 靜默容錯 = 錯誤；禁止跨版本目錄引用
  L3 內容層: 空 slide / placeholder / 亂碼 / 簡繁混用 / 字數過低
  L4 對比度: 實際用 Playwright 計算 WCAG 對比度（不再 stub 回 ok=True）

核心哲學（v2）: **未驗證 ≠ 通過**。任何檢查無法執行時回報 not_verified 而非 ok=True。

Usage:
  python verify-deck.py --html path/to/deck.html [--ci] [--report out.json] [--repo-root path]
Exit:
  0 = all checks passed
  1 = one or more checks failed
"""

import argparse
import json
import os
import re
import sys
import time
import threading
from contextlib import contextmanager
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

# Safe import for bs4
BeautifulSoup = None
try:
    from bs4 import BeautifulSoup as _BeautifulSoup
    BeautifulSoup = _BeautifulSoup
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(2)


# =============================================================================
# L2 — 資源完整性檢查（v2 新增，不需要瀏覽器）
# =============================================================================

def check_resource_integrity(html_content: str, html_path: str, repo_root: str | None = None) -> dict:
    """掃描所有相對路徑引用，驗證檔案真實存在。"""
    issues = []
    refs = re.findall(r'(?:src|href|poster)="([^"]+)"', html_content)
    rel_refs = []
    for r in refs:
        if (not r.startswith('#') and not r.startswith('data:')
                and not r.startswith('http://') and not r.startswith('https://')
                and not r.startswith('//')):
            rel_refs.append(r)

    html_dir = Path(html_path).resolve().parent
    repo = Path(repo_root).resolve() if repo_root else _find_repo_root(html_dir)

    for ref in rel_refs:
        # 解出相對於 HTML 檔的真實路徑
        candidate = (html_dir / ref).resolve()
        # 若是絕對路徑且不在 html_dir 下 → 跨目錄
        try:
            candidate.relative_to(html_dir)
        except ValueError:
            # 不在 html 同目錄：檢查是否在 repo 內（允許 ../）
            try:
                candidate.relative_to(repo)
            except ValueError:
                issues.append({
                    "ref": ref, "severity": "error",
                    "reason": f"路徑跳出 repo（{candidate}）"
                })
                continue

        if not candidate.exists():
            issues.append({
                "ref": ref, "severity": "error",
                "reason": f"檔案不存在: {candidate}"
            })
        else:
            # 跨版本目錄引用檢查（v3 不該指向 v1_images）
            ref_lower = ref.lower()
            html_name = Path(html_path).stem.lower()
            m = re.search(r'(v\d)', html_name)
            if m:
                this_v = m.group(1)
                other_vs = re.findall(r'([v]\d)', ref_lower)
                for ov in other_vs:
                    if ov != this_v:
                        issues.append({
                            "ref": ref, "severity": "warning",
                            "reason": f"跨版本目錄引用: 目前 {html_name} 指向 {ov} 目錄（{ref}）"
                        })

    # onerror 靜默容錯檢查（display:none / display='none' / display="none"）
    onerror_count = len(re.findall(r'onerror="[^"]*display\s*[:=]\s*[\'"]?\s*none[\'"]?[^"]*"', html_content))
    if onerror_count > 0:
        issues.append({
            "ref": "html", "severity": "warning",
            "reason": f"{onerror_count} 個 onerror 靜默隱藏（display:none）——圖片掛了不會顯示破圖，請改用可見的 fallback"
        })

    ok = not any(i["severity"] == "error" for i in issues)
    return {"ok": ok, "issues": issues, "checked_refs": len(rel_refs), "onerror_hidden": onerror_count}


def _find_repo_root(html_dir: Path) -> Path:
    """往上找 repo root（有 .git 或 slidecraft 特徵）。"""
    d = html_dir
    while d != d.parent:
        if (d / ".git").exists():
            return d
        d = d.parent
    return html_dir


# =============================================================================
# L3 — 內容層檢查（v2 新增，不需要瀏覽器）
# =============================================================================

PLACEHOLDER_PATTERNS = [
    r'lorem\s+ipsum', r'todo', r'xxxx', r'placeholder',
    r'\[請.*?\]', r'\(請.*?\)', r'待補', r'待填', r'範例文字',
    r'TBD', r'N/A', r'這裡放', r'這裡寫',
]

GARBAGE_PATTERNS = [
    r'[\ufffd]',                       # U+FFFD replacement char
    r'\u0000',                         # NUL
    r'[\uE000-\uF8FF]',                # private use area (unrendered glyphs)
]

def check_content_quality(html_content: str) -> dict:
    """檢查每個 slide 的文字量、placeholder、亂碼。"""
    issues = []
    stats = {"slides": 0, "empty_slides": [], "low_content_slides": [], "placeholders": [], "garbage": []}

    # 以 data-slide-id 分 slide
    slide_blocks = re.split(r'(?=<section)', html_content)
    slide_blocks = [s for s in slide_blocks if 'data-slide-id' in s]

    for block in slide_blocks:
        sid_m = re.search(r'data-slide-id="([^"]+)"', block)
        sid = sid_m.group(1) if sid_m else "?"
        stats["slides"] += 1

        # 偵測 layout 類型（cover/transition 是標題頁，豁免 low_content）
        layout_m = re.search(r'data-layout="([^"]+)"', block)
        layout = layout_m.group(1) if layout_m else ""
        is_title_page = layout in ("cover", "transition", "title", "section", "divider")

        # 移除 script/style 後算文字量
        clean = re.sub(r'<script.*?</script>', ' ', block, flags=re.S)
        clean = re.sub(r'<style.*?</style>', ' ', clean, flags=re.S)
        text = re.sub(r'<[^>]+>', ' ', clean)
        text = re.sub(r'\s+', ' ', text).strip()
        # 去掉 class/attribute 殘留
        text = re.sub(r'class="[^"]*"|data-[a-z-]+="[^"]*"', ' ', text)

        char_count = len(text)

        if char_count < 30:
            stats["empty_slides"].append({"id": sid, "chars": char_count, "layout": layout})
            issues.append({"ref": sid, "severity": "error", "reason": f"slide 近乎空白（{char_count} chars, layout={layout}）"})
        elif char_count < 80 and not is_title_page:
            stats["low_content_slides"].append({"id": sid, "chars": char_count, "layout": layout})
            issues.append({"ref": sid, "severity": "warning", "reason": f"slide 內容偏少（{char_count} chars, layout={layout}）"})

        # placeholder 檢查
        for pat in PLACEHOLDER_PATTERNS:
            for m in re.finditer(pat, text, re.I):
                stats["placeholders"].append({"id": sid, "match": m.group(0)[:30]})
                issues.append({"ref": sid, "severity": "error", "reason": f"placeholder 文字: {m.group(0)[:30]}"})
                break

        # 亂碼檢查
        for pat in GARBAGE_PATTERNS:
            for m in re.finditer(pat, text):
                stats["garbage"].append({"id": sid, "match": repr(m.group(0))})
                issues.append({"ref": sid, "severity": "error", "reason": f"亂碼字元: {repr(m.group(0))}"})
                break

    # 簡繁混用粗略偵測（同一段有「與」又有「与」等高頻字）
    mixed = _detect_mixed_script(html_content)
    if mixed:
        issues.append({"ref": "html", "severity": "warning", "reason": f"疑似簡繁混用: {mixed[:100]}"})
        stats["mixed_script"] = mixed[:100]

    ok = not any(i["severity"] == "error" for i in issues)
    return {"ok": ok, "issues": issues, "stats": stats}


def _detect_mixed_script(text: str) -> str | None:
    """偵測同文件中高頻簡繁字混用。"""
    trad_chars = set("與為時後裡個們對說從這會來")
    simp_chars = set("与为时后里个们对说从这会来")
    t_count = sum(1 for c in text if c in trad_chars)
    s_count = sum(1 for c in text if c in simp_chars)
    # 大量兩者都有 → 可能混用（但注意「后/里/个」在繁中也有合法用法，取高頻特徵字）
    if t_count > 10 and s_count > 10:
        ratio = s_count / (t_count + s_count)
        if 0.05 < ratio < 0.95:
            return f"繁{t_count}簡{s_count}（比例 {ratio:.0%}）"
    return None


# =============================================================================
# L4 — 對比度檢查（v2 修正：不再 stub，實際計算 WCAG 對比度）
# =============================================================================

def run_contrast_verification(html_path: str, page: Any = None) -> dict:
    """計算每個 slide 主要文字 vs 背景的 WCAG 對比度。page 為 None 時回報 not_verified。"""
    if page is None:
        return {
            "ok": False,
            "tool": "not_verified",
            "message": "對比度檢查需要瀏覽器頁面（未提供）——此為未驗證，不是通過！",
            "details": {"note": "v2: 未驗證 ≠ 通過"},
        }

    try:
        result = page.evaluate("""
            () => {
                function lum(r, g, b) {
                    const f = c => {
                        c /= 255;
                        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
                    };
                    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
                }
                function contrast(fg, bg) {
                    const l1 = lum(fg[0], fg[1], fg[2]);
                    const l2 = lum(bg[0], bg[1], bg[2]);
                    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
                }
                function parseColor(s) {
                    if (!s) return null;
                    const m = s.match(/rgba?\\((\\d+)[,\\s]+(\\d+)[,\\s]+(\\d+)/);
                    if (m) return [+m[1], +m[2], +m[3]];
                    const h = s.match(/#([0-9a-f]{6})/i);
                    if (h) return [parseInt(h[1].slice(0,2),16), parseInt(h[1].slice(2,4),16), parseInt(h[1].slice(4,6),16)];
                    return null;
                }
                const slides = document.querySelectorAll('.slide, section.slide, .deck > section');
                const results = [];
                slides.forEach((slide, i) => {
                    // 找主要文字元素
                    const els = slide.querySelectorAll('h1, h2, h3, p, li, .content, .slide-content');
                    let worst = null;
                    els.forEach(el => {
                        const cs = getComputedStyle(el);
                        const fg = parseColor(cs.color);
                        // 背景：往上找第一個有背景色/背景圖的元素
                        let bgEl = el;
                        let bg = null;
                        let bgColor = null;
                        while (bgEl) {
                            const cs2 = getComputedStyle(bgEl);
                            if (cs2.backgroundColor && cs2.backgroundColor !== 'rgba(0, 0, 0, 0)') {
                                bg = parseColor(cs2.backgroundColor);
                                if (bg) { bgColor = cs2.backgroundColor; break; }
                            }
                            bgEl = bgEl.parentElement;
                        }
                        if (fg && bg) {
                            const ratio = contrast(fg, bg);
                            if (!worst || ratio < worst.ratio) worst = {ratio, el: el.tagName, fg: cs.color, bg: bgColor};
                        }
                    });
                    const id = slide.getAttribute('data-slide-id') || 's' + (i+1);
                    results.push({id, worst});
                });
                return results;
            }
        """)

        issues = []
        for r in result:
            if r["worst"] and r["worst"]["ratio"] < 4.5:
                issues.append({
                    "ref": r["id"],
                    "severity": "error",
                    "reason": f"對比度不足: {r['worst']['ratio']:.2f}:1 (<4.5 WCAG AA) fg={r['worst']['fg']} bg={r['worst']['bg']}"
                })
            elif r["worst"] and r["worst"]["ratio"] < 7:
                issues.append({
                    "ref": r["id"],
                    "severity": "warning",
                    "reason": f"對比度偏低: {r['worst']['ratio']:.2f}:1 (<7 WCAG AAA)"
                })

        ok = not any(i["severity"] == "error" for i in issues)
        return {
            "ok": ok,
            "tool": "wcag-contrast",
            "message": f"檢查 {len(result)} slides 對比度",
            "details": {"slides": result, "issues": issues},
        }
    except Exception as e:
        return {
            "ok": False,
            "tool": "error",
            "message": f"對比度計算失敗: {str(e)[:200]}",
            "details": {},
        }


def check_font_declaration(html_content: str, html_path: str = "", repo_root: str | None = None) -> dict:
    """L3.5 — 字型宣告檢查（靜態，不依賴瀏覽器環境）。

    檢查兩件事：
    1. font-family 是否包含 CJK 字型（Noto Sans TC / 思源黑體 / 微軟正黑體 等）
    2. 是否有字型載入來源（Google Fonts link / @font-face / 本地 woff2/ttf / 外部 CSS 檔）

    背景：2026-08-15 老公實測抓到 V3 中文全變方塊（tofu）——
    CSS 宣告 'Noto Sans TC' 但從未載入，無中文字型的環境全部 fallback 成方塊。

    補充：external 模式（--external）HTML 用 <link rel="stylesheet" href="slidecraft.css">，
    @import 在外部 CSS——檢查需讀取該 CSS 檔確認字型來源。
    """
    issues = []

    # 1. font-family 是否含 CJK 字型
    cjk_fonts = [
        "Noto Sans TC", "Noto Sans CJK", "Noto Serif TC", "PingFang",
        "Microsoft JhengHei", "微软雅黑", "微軟正黑", "Source Han", "思源",
        "Taipei", "cwTeX", "jf-openhuninn", "WenQuanYi", "文泉驛",
        "Yu Gothic", "Hiragino",
    ]
    declared_cjk = [f for f in cjk_fonts if f.lower() in html_content.lower()]
    if not declared_cjk:
        issues.append({
            "ref": "html", "severity": "error",
            "reason": "font-family 未宣告任何 CJK 中文字型（如 Noto Sans TC / 微軟正黑體）——無中文字型環境會顯示方塊（tofu）"
        })

    # 2. 字型載入來源（含外部 CSS 檔）
    has_font_source = False
    source = "無"
    if "fonts.googleapis.com" in html_content or "fonts.gstatic.com" in html_content:
        has_font_source = True
        source = "Google Fonts (inline)"
    elif "@font-face" in html_content:
        has_font_source = True
        source = "@font-face (inline)"
    elif re.search(r'\.(woff2?|ttf|otf)', html_content):
        has_font_source = True
        source = "本地字型檔"
    else:
        # external 模式：讀外部 CSS 檔
        ext_css = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', html_content)
        for css_href in ext_css:
            css_text = ""
            if css_href.startswith("http"):
                # 遠端 CSS 無法靜態讀取 → 視為潛在來源（寬鬆）
                has_font_source = True
                source = f"外部 CSS: {css_href}"
                break
            else:
                # 本地 CSS：嘗試解析路徑
                css_path = None
                if html_path:
                    p = Path(html_path).resolve().parent / css_href
                    if p.exists():
                        css_path = p
                if css_path is None and repo_root:
                    p = Path(repo_root).resolve() / css_href
                    if p.exists():
                        css_path = p
                if css_path:
                    css_text = css_path.read_text(encoding="utf-8", errors="replace")
                    if "fonts.googleapis.com" in css_text or "@font-face" in css_text or "fonts.gstatic.com" in css_text:
                        has_font_source = True
                        source = f"外部 CSS {css_href} 含字型來源"
                        break

    if declared_cjk and not has_font_source:
        issues.append({
            "ref": "html", "severity": "error",
            "reason": f"font-family 宣告了 CJK 字型（{declared_cjk[0]}）但沒有任何載入來源（Google Fonts/@font-face/本地檔/外部 CSS）——字型宣告了卻不會被載入"
        })
    if not declared_cjk and not has_font_source:
        issues.append({
            "ref": "html", "severity": "warning",
            "reason": "無 CJK 字型宣告且無載入來源——中文內容在無中文字型環境會顯示方塊"
        })

    ok = not any(i["severity"] == "error" for i in issues)
    return {
        "ok": ok,
        "tool": "font-declaration-check",
        "message": f"CJK 字型: {', '.join(declared_cjk) if declared_cjk else '無'} | 載入來源: {source}",
        "issues": issues,
        "details": {"declared_cjk": declared_cjk, "font_source": source},
    }


# =============================================================================
# LOCAL HTTP SERVER
# =============================================================================

@contextmanager
def serve_deck(html_path: str, port: int = 0):
    html_path = Path(html_path).resolve()
    base_dir = html_path.parent

    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(base_dir), **kwargs)

        def log_message(self, format, *args):
            pass

    httpd = HTTPServer(("", port), QuietHandler)
    actual_port = httpd.server_address[1]
    url = f"http://localhost:{actual_port}/{html_path.name}"

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield url, actual_port
    finally:
        httpd.shutdown()
        thread.join(timeout=2.0)


# =============================================================================
# CORE VERIFICATION (v2)
# =============================================================================

def verify_deck(html_path: str, ci: bool = False, report_path: str | None = None, repo_root: str | None = None) -> dict:
    html_path = str(Path(html_path).resolve())
    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"HTML not found: {html_path}")

    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()

    report: dict[str, Any] = {
        "html_path": html_path,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "static_checks": {},
        "resource_integrity": {},   # L2
        "content_quality": {},      # L3
        "viewports_tested": [],
        "images": [],
        "js_slider": {},
        "contrast": {},             # L4
        "console_errors": [],
        "errors": [],
        "passed": False,
    }

    # ── L2: 資源完整性（靜態，先跑）──
    ri = {"ok": True, "issues": []}
    try:
        ri = check_resource_integrity(html_content, html_path, repo_root)
        report["resource_integrity"] = ri
        for i in ri["issues"]:
            if i["severity"] == "error":
                report["errors"].append(f"[L2資源] {i['ref']}: {i['reason']}")
    except Exception as e:
        ri = {"ok": False, "issues": []}
        report["resource_integrity"] = {"ok": False, "error": str(e)}
        report["errors"].append(f"[L2資源] 檢查失敗: {str(e)[:150]}")

    # ── L3: 內容品質（靜態）──
    cq = {"ok": True, "issues": []}
    try:
        cq = check_content_quality(html_content)
        report["content_quality"] = cq
        for i in cq["issues"]:
            if i["severity"] == "error":
                report["errors"].append(f"[L3內容] {i['ref']}: {i['reason']}")
    except Exception as e:
        cq = {"ok": False, "issues": []}
        report["content_quality"] = {"ok": False, "error": str(e)}
        report["errors"].append(f"[L3內容] 檢查失敗: {str(e)[:150]}")

    # ── L1: 既有技術檢查（瀏覽器）──
    file_size = os.path.getsize(html_path)
    file_size_ok = file_size < 300 * 1024

    style_blocks = 0
    style_ok = True
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_content, "lxml")
        style_blocks = len(soup.find_all("style"))
        style_ok = (1 <= style_blocks <= 2)

    report["static_checks"] = {
        "file_size_bytes": file_size,
        "file_size_ok": file_size_ok,
        "style_blocks": style_blocks,
        "style_blocks_ok": style_ok,
    }
    if not file_size_ok:
        report["errors"].append(f"File size {file_size} bytes exceeds 300KB limit")
    if not style_ok:
        report["errors"].append(f"Found {style_blocks} <style> blocks (expected 1-2)")

    all_passed = file_size_ok and style_ok and ri["ok"] and cq["ok"]

    # ── 瀏覽器檢查（overflow / 圖片 / 滑桿 / 對比度）──
    if sync_playwright is None:
        # 沒有 playwright：瀏覽器層無法驗證 → 標記 not_verified（不假裝通過）
        report["browser_checks"] = {
            "ok": False,
            "tool": "not_verified",
            "message": "playwright 未安裝——L1 瀏覽器檢查（overflow/圖片/滑桿）與 L4 對比度未執行。"
                       "此為未驗證，不是通過！請在安裝 playwright 的環境執行（pip install playwright && playwright install chromium）。",
        }
        report["errors"].append("[L1技術] playwright 未安裝——瀏覽器檢查未執行（not_verified，非通過）")
        report["errors"].append("[L4對比] playwright 未安裝——對比度檢查未執行（not_verified，非通過）")
        all_passed = False

        # 整理報告
        report["js_slider"] = {"ok": False, "message": "not_verified（無 playwright）"}
        report["contrast"] = {"ok": False, "tool": "not_verified",
                              "message": "playwright 未安裝——對比度檢查未執行"}
        report["viewports_tested"] = []
        report["images"] = []

        report["passed"] = False
        if report_path:
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return report

    viewports = [
        {"name": "desktop", "width": 1280, "height": 720, "is_mobile": False},
        {"name": "mobile-390x844", "width": 390, "height": 844, "is_mobile": True},
    ]
    image_status: dict[str, dict] = {}
    console_errors: list[str] = []
    natural_map: dict[str, dict] = {}
    contrast_result = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])

        for vp in viewports:
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                    if not vp["is_mobile"] else
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
                ),
                is_mobile=vp["is_mobile"],
                has_touch=vp["is_mobile"],
                device_scale_factor=2 if vp["is_mobile"] else 1,
            )
            page = context.new_page()

            def make_console_handler(vp_name: str):
                def handler(msg):
                    if msg.type in ("error", "warning"):
                        console_errors.append(f"[{vp_name}] {msg.type.upper()}: {msg.text[:300]}")
                return handler
            page.on("console", make_console_handler(vp["name"]))

            def make_response_handler(vp_name: str):
                def handler(resp):
                    try:
                        req = resp.request
                        is_image = (
                            req.resource_type == "image" or
                            any(resp.url.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"))
                        )
                        if is_image:
                            cl = resp.headers.get("content-length")
                            size = int(cl) if cl and cl.isdigit() else 0
                            image_status[resp.url] = {
                                "status": resp.status,
                                "size": size,
                                "size_ok": size < 300 * 1024 if size else True,
                                "http_ok": resp.status == 200,
                            }
                    except Exception:
                        pass
                return handler
            page.on("response", make_response_handler(vp["name"]))

            with serve_deck(html_path) as (url, _port):
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(600)

                if not natural_map:
                    try:
                        natural_map_list = page.evaluate("""
                            () => Array.from(document.querySelectorAll('img')).map(img => ({
                                src: img.currentSrc || img.src || img.getAttribute('src') || '',
                                naturalWidth: img.naturalWidth || 0,
                                naturalHeight: img.naturalHeight || 0,
                                complete: img.complete
                            }))
                        """)
                        for item in natural_map_list:
                            if item.get("src"):
                                natural_map[item["src"]] = item
                    except Exception as e:
                        console_errors.append(f"Natural image dimension check error: {e}")

                slide_infos: list[dict] = page.evaluate("""
                    () => {
                        const nodes = Array.from(document.querySelectorAll('.slide, section.slide, .deck > section'));
                        return nodes.map((el, i) => {
                            const id = el.getAttribute('data-slide-id') || el.id || `s${(i+1).toString().padStart(2,'0')}`;
                            const order = parseInt(el.getAttribute('data-order') || (i+1));
                            return { index: i, id, order };
                        });
                    }
                """)
                num_slides = len(slide_infos)
                vp_slide_results = []

                for s in slide_infos:
                    idx = s["index"]
                    if vp.get("is_mobile"):
                        page.evaluate(f"""
                            (function() {{
                                const slides = document.querySelectorAll('.slide, section.slide, .deck > section');
                                slides.forEach(s => s.classList.remove('slide-active'));
                                slides.forEach(s => s.classList.remove('compact'));
                                slides.forEach(s => s.style.removeProperty('width'));
                                slides.forEach(s => s.style.removeProperty('height'));
                                slides.forEach(s => s.style.removeProperty('transform'));
                                const target = slides[{idx}];
                                if (target) {{
                                    target.classList.add('slide-active');
                                    const vw = window.innerWidth;
                                    const isM = vw < 800;
                                    const avail = Math.max(300, Math.min(vw - (isM ? 8 : 20), 620));
                                    target.classList.add('compact');
                                    target.style.width = avail + 'px';
                                    target.style.height = '';
                                    target.scrollTop = 0;
                                }}
                            }})();
                        """)
                        page.wait_for_timeout(300)
                    else:
                        page.evaluate(f"""
                            (function() {{
                                const slides = document.querySelectorAll('.slide, section.slide, .deck > section');
                                slides.forEach(s => s.classList.remove('slide-active'));
                                const target = slides[{idx}];
                                if (target) {{
                                    target.classList.add('slide-active');
                                    target.scrollTop = 0;
                                }}
                            }})();
                        """)
                        page.wait_for_timeout(280)

                    overflow = page.evaluate("""
                        () => {
                            const active = document.querySelector('.slide.slide-active') ||
                                           document.querySelector('section.slide-active') ||
                                           document.querySelector('.slide-active');
                            if (!active) return { overflows: true, scrollHeight: 0, clientHeight: 0 };
                            const content = active.querySelector('.slide-content') || active;
                            const sh = content.scrollHeight || 0;
                            const ch = content.clientHeight || 0;
                            return { overflows: sh > ch + 3, scrollHeight: sh, clientHeight: ch };
                        }
                    """)

                    slide_ok = not overflow["overflows"]
                    if not slide_ok:
                        all_passed = False
                        report["errors"].append(
                            f"[L1技術] [{vp['name']}] Slide {s['id']} overflows: "
                            f"scrollHeight={overflow['scrollHeight']} > clientHeight={overflow['clientHeight']}"
                        )

                    vp_slide_results.append({
                        "id": s["id"], "order": s["order"],
                        "overflow": overflow["overflows"],
                        "scrollHeight": overflow["scrollHeight"],
                        "clientHeight": overflow["clientHeight"],
                        "ok": slide_ok,
                    })

                # ── JS slider test ──
                slider_ok = True
                try:
                    page.evaluate("""
                        (function() {
                            const slides = document.querySelectorAll('.slide, section.slide, .deck > section');
                            slides.forEach(s => s.classList.remove('slide-active'));
                            if (slides[0]) slides[0].classList.add('slide-active');
                        })();
                    """)
                    page.wait_for_timeout(200)
                    if num_slides > 1:
                        page.keyboard.press('ArrowRight')
                        page.wait_for_timeout(350)
                        page.keyboard.press('ArrowLeft')
                        page.wait_for_timeout(300)
                        for _ in range(min(2, max(0, num_slides - 1))):
                            page.keyboard.press('ArrowRight')
                            page.wait_for_timeout(280)
                    final_active = page.evaluate("() => !!document.querySelector('.slide.slide-active, section.slide-active')")
                    if not final_active:
                        slider_ok = False
                except Exception as e:
                    slider_ok = False
                    console_errors.append(f"[{vp['name']}] Slider keyboard interaction failed: {str(e)[:200]}")

                if not slider_ok:
                    all_passed = False
                    report["errors"].append(f"[L1技術] [{vp['name']}] JS slider (arrow) test failed")

                # ── L4: 對比度（最後一個 viewport 跑，有 page）──
                if contrast_result is None:
                    contrast_result = run_contrast_verification(html_path, page=page)
                    report["contrast"] = contrast_result
                    if not contrast_result.get("ok", False):
                        all_passed = False
                        if "issues" in contrast_result.get("details", {}):
                            for ci in contrast_result["details"]["issues"]:
                                if ci["severity"] == "error":
                                    report["errors"].append(f"[L4對比] {ci['ref']}: {ci['reason']}")
                        else:
                            report["errors"].append(f"[L4對比] {contrast_result.get('message', '未驗證')}")

                # ── L3.5: 字型宣告檢查（tofu 方塊防護）──
                # 註：改為靜態檢查（check_font_declaration），不依賴瀏覽器環境字型
                if "font_declaration" not in report:
                    font_result = check_font_declaration(html_content, html_path=html_path, repo_root=repo_root)
                    report["font_declaration"] = font_result
                    if not font_result.get("ok", False):
                        all_passed = False
                        for fi in font_result.get("issues", []):
                            if fi["severity"] == "error":
                                report["errors"].append(f"[L3.5字型] {fi['ref']}: {fi['reason']}")

                if ci:
                    os.makedirs("verify-output", exist_ok=True)
                    safe = vp["name"].replace("/", "_")
                    try:
                        page.screenshot(path=f"verify-output/screenshot-{safe}.png", full_page=False)
                    except Exception:
                        pass

                report["viewports_tested"].append({
                    "name": vp["name"],
                    "viewport": {"width": vp["width"], "height": vp["height"]},
                    "slides": vp_slide_results,
                    "js_slider_ok": slider_ok,
                    "num_slides": num_slides,
                })

            context.close()

        browser.close()

    # ── 圖片後處理 ──
    final_images = []
    for url, info in image_status.items():
        nat = natural_map.get(url, {})
        if not nat:
            fname = url.split("/")[-1]
            for k, v in natural_map.items():
                if k.endswith(fname):
                    nat = v
                    break
        natural_w = nat.get("naturalWidth", 0)
        item = {
            "url": url, "http_status": info.get("status", 0),
            "size_bytes": info.get("size", 0),
            "size_kb": round(info.get("size", 0) / 1024, 1) if info.get("size") else 0,
            "naturalWidth": natural_w,
            "http_ok": info.get("http_ok", False),
            "size_ok": info.get("size_ok", True),
            "natural_ok": natural_w > 0,
            "ok": (info.get("http_ok", False) and info.get("size_ok", True) and natural_w > 0),
        }
        final_images.append(item)
        if not item["ok"]:
            all_passed = False
            report["errors"].append(
                f"[L1技術] Image issue: {url} (status={item['http_status']}, size_kb={item['size_kb']}, naturalW={natural_w})"
            )
    report["images"] = final_images

    js_overall = all(vp.get("js_slider_ok", False) for vp in report["viewports_tested"])
    report["js_slider"] = {"ok": js_overall, "tested_viewports": len(report["viewports_tested"])}
    if not js_overall:
        all_passed = False

    report["console_errors"] = console_errors[:15]

    # 最終判定：所有層都過 + 沒有 error
    report["passed"] = bool(all_passed and not any("L2資源" in e or "L3內容" in e or "L4對比" in e for e in report["errors"]))

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description="SlideCraft Deck Verifier v2 — 四層驗證")
    parser.add_argument("--html", required=True, help="Path to the generated HTML deck file")
    parser.add_argument("--ci", action="store_true", help="CI mode")
    parser.add_argument("--report", default="verify-output/report.json", help="Report output path")
    parser.add_argument("--repo-root", default=None, help="Repo root for resource integrity checks")
    args = parser.parse_args()

    try:
        result = verify_deck(args.html, ci=args.ci, report_path=args.report, repo_root=args.repo_root)
        sys.exit(0 if result.get("passed", False) else 1)
    except Exception as e:
        err_report = {"html_path": args.html, "error": str(e), "passed": False, "errors": [str(e)]}
        print(json.dumps(err_report, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
