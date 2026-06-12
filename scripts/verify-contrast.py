#!/usr/bin/env python3
"""
SlideCraft Contrast Verification Script
========================================
Loads a rendered HTML deck with Playwright + Chromium, inspects every slide's
text elements, and computes WCAG AA (4.5:1) contrast ratios.

Usage:
    python scripts/verify-contrast.py output/deck.html [--json report.json]
    python scripts/verify-contrast.py https://example.com/deck.html

Exit code: 0 if all pass, 1 if any failures.
"""
import sys, json, os, re

# ─── WCAG contrast math ─────────────────────────────────────────────────

def srgb_to_linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4

def relative_luminance(r: float, g: float, b: float) -> float:
    return (0.2126 * srgb_to_linear(r/255) +
            0.7152 * srgb_to_linear(g/255) +
            0.0722 * srgb_to_linear(b/255))

def contrast_ratio(fg: tuple, bg: tuple) -> float:
    l1, l2 = relative_luminance(*fg), relative_luminance(*bg)
    return (max(l1,l2)+0.05)/(min(l1,l2)+0.05)

# ─── Multiple-slide JS evaluator (avoids f-string issues) ───────────────

CHECK_JS = """
() => {
    const slides = document.querySelectorAll('.slide');
    const results = [];

    function parseRgb(s) {
        const m = s.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
        return m ? [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])] : [0,0,0];
    }
    function luminance(r,g,b) {
        const toLin = c => c <= 0.04045 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4);
        return 0.2126*toLin(r/255) + 0.7152*toLin(g/255) + 0.0722*toLin(b/255);
    }
    function contrastRatio(fg, bg) {
        const l1 = luminance(fg[0],fg[1],fg[2]);
        const l2 = luminance(bg[0],bg[1],bg[2]);
        return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    }

    slides.forEach(slide => {
        const order = slide.getAttribute('data-order');
        const hasBg = slide.hasAttribute('data-has-bg');
        const hasDarkBg = slide.hasAttribute('data-has-dark-bg');
        const layout = slide.getAttribute('data-layout') || '?';
        const texts = slide.querySelectorAll('h1, h2, h3, li, p, .stat-value, .stat-label, .subtitle');
        const checks = [];
        let pass = true;

        texts.forEach(el => {
            const text = (el.textContent || '').trim().substring(0, 40);
            if (text.length < 3) return;

            const style = window.getComputedStyle(el);
            const color = style.color;
            const shadow = style.textShadow;
            const fs = parseFloat(style.fontSize);
            const fw = parseInt(style.fontWeight);

            const card = el.closest('.card');
            const statEl = el.closest('.stat');
            let bgColor;
            if (card) {
                bgColor = window.getComputedStyle(card).backgroundColor;
            } else if (statEl) {
                bgColor = window.getComputedStyle(statEl).backgroundColor;
            } else if (hasBg || hasDarkBg) {
                bgColor = 'rgb(40,40,45)';  // dark overlay
            } else {
                bgColor = window.getComputedStyle(slide).backgroundColor;
            }

            const fg = parseRgb(color);
            const bg = parseRgb(bgColor);
            const ratio = contrastRatio(fg, bg);

            const isLarge = fs >= 24 || (fs >= 18 && fw >= 700);
            const required = isLarge ? 3.0 : 4.5;
            const hasShadow = shadow && shadow !== 'none' && !shadow.startsWith('0px 0px 0px');
            const isWhite = color === 'rgb(255, 255, 255)' || color === 'rgba(255, 255, 255, 0.9)';
            const onBgSlide = hasBg || hasDarkBg;
            const inCard = !!card;
            const inStat = !!statEl;

            let status = 'PASS';
            // Non-card/non-stat text on bg slides must be white
            if (onBgSlide && !inCard && !inStat && !isWhite && text.length > 3) {
                status = 'FAIL';
            }
            // Element on white card/stat bg: check actual contrast vs its bg
            if (inCard || inStat) {
                const itemBg = parseRgb(bgColor);
                const itemRatio = contrastRatio(fg, itemBg);
                if (itemRatio < required && text.length > 3) {
                    status = 'FAIL';
                }
            } else if (!isWhite) {
                // Non-white on bg slide or theme bg — check contrast
                if (ratio < required && text.length > 3) {
                    status = 'FAIL';
                }
            }

            if (status !== 'PASS') pass = false;
            checks.push({
                text, tag: el.tagName, inCard, color, bgColor,
                ratio: Math.round(ratio * 100) / 100,
                required, hasShadow, status
            });
        });

        results.push({slide: order, layout, hasBg, hasDarkBg, pass, checks});
    });
    return results;
}
"""

def verify_deck(path: str) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        if path.startswith("http"):
            page.goto(path, wait_until="networkidle")
        else:
            page.goto(f"file://{os.path.abspath(path)}", wait_until="networkidle")
        page.wait_for_timeout(1500)

        slides = page.evaluate(CHECK_JS)
        browser.close()

    all_pass = all(s["pass"] for s in slides)
    return {"pass": all_pass, "slides": slides, "total": len(slides)}

# ─── Reporting ──────────────────────────────────────────────────────────

def print_report(report: dict):
    passed = sum(1 for s in report["slides"] if s["pass"])
    failed = report["total"] - passed
    print(f"\n{'='*60}")
    print(f"  SlideCraft Contrast Verification")
    print(f"  {report['total']} slides | {passed} PASS ✅ | {failed} FAIL ❌")
    print(f"{'='*60}\n")
    for s in report["slides"]:
        icon = "✅" if s["pass"] else "❌"
        bg = "BG" if s["hasBg"] else ("DARK" if s["hasDarkBg"] else "theme")
        print(f"  {icon} Slide {s['slide']:>2} [{bg:>5}] [{s['layout']:<14}]")
        for c in s["checks"]:
            if c["status"] != "PASS":
                loc = "[card]" if c["inCard"] else "[bg]"
                ratio = f" {c['ratio']}:1 (need {c['required']})"
                shad = "" if c["hasShadow"] else " NO-SHADOW"
                print(f"       <{c['tag']}> \"{c['text']}\"{loc} fg={c['color']}{ratio}{shad}")
    print()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify WCAG contrast for a SlideCraft deck")
    parser.add_argument("html", help="Path to .html or URL")
    parser.add_argument("--json", help="Save JSON report")
    args = parser.parse_args()

    report = verify_deck(args.html)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  📄 Report saved: {args.json}")

    print_report(report)
    sys.exit(0 if report["pass"] else 1)

if __name__ == "__main__":
    main()
