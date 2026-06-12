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

# ─── Multiple-slide JS evaluator ───────────────────────────────────────
#
# Key features:
#   - Parses the actual overlay gradient from each slide's inline <style>
#     to compute the EFFECTIVE background pixel (worst case: white image
#     under a black overlay at the LIGHTEST gradient stop).
#   - NO auto-pass for white/near-white text — every element gets a real
#     contrast ratio check.
#   - Card/stat elements are checked against their actual card bg color.
#

CHECK_JS = """
() => {
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

    // Parse the slide's inline style to extract the LIGHTEST overlay stop.
    // We assume worst case: the background image is white, so
    // effectivePixel = 255 * (1 - minOpacity).
    function getEffectiveBg(slide) {
        const style = slide.getAttribute('style') || '';
        // Match all rgba(N,N,N,D.DD) in the gradient
        const rgbaRe = /rgba\\s*\\(\\s*0\\s*,\\s*0\\s*,\\s*0\\s*,\\s*([\\d.]+)\\s*\\)/g;
        const matches = [];
        let m;
        while ((m = rgbaRe.exec(style)) !== null) {
            matches.push(parseFloat(m[1]));
        }
        if (matches.length >= 1) {
            // Use the MINIMUM opacity (lightest part of gradient = worst case)
            const minOpa = Math.min(...matches);
            const val = Math.round(255 * (1 - minOpa));
            return [val, val, val];
        }
        // Fallback for data-has-dark-bg slides (no image, just dark bg)
        if (slide.hasAttribute('data-has-dark-bg'))
            return [40, 40, 45];
        // Theme slide (no bg image) — use computed background color
        const cs = window.getComputedStyle(slide);
        const bgMatch = cs.backgroundColor.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
        return bgMatch ? [parseInt(bgMatch[1]), parseInt(bgMatch[2]), parseInt(bgMatch[3])] : [255,255,255];
    }

    const slides = document.querySelectorAll('.slide');
    const results = [];

    slides.forEach(slide => {
        const order = slide.getAttribute('data-order');
        const hasBg = slide.hasAttribute('data-has-bg');
        const hasDarkBg = slide.hasAttribute('data-has-dark-bg');
        const layout = slide.getAttribute('data-layout') || '?';
        const texts = slide.querySelectorAll('h1, h2, h3, li, p, .stat-value, .stat-label, .subtitle');
        const checks = [];
        let pass = true;

        const effectiveBg = getEffectiveBg(slide);

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
            const inCard = !!card;
            const inStat = !!statEl;
            const onBgSlide = hasBg || hasDarkBg;

            let computedBg;
            let bgPixels;
            if (inCard) {
                computedBg = window.getComputedStyle(card).backgroundColor;
                bgPixels = parseRgb(computedBg);
            } else if (inStat) {
                computedBg = window.getComputedStyle(statEl).backgroundColor;
                bgPixels = parseRgb(computedBg);
            } else {
                bgPixels = effectiveBg;
                computedBg = 'rgb(' + effectiveBg[0] + ',' + effectiveBg[1] + ',' + effectiveBg[2] + ')';
            }

            const fg = parseRgb(color);
            const ratio = contrastRatio(fg, bgPixels);

            const isLarge = fs >= 24 || (fs >= 18 && fw >= 700);
            const required = isLarge ? 3.0 : 4.5;
            const hasShadow = shadow && shadow !== 'none' && !shadow.startsWith('0px 0px 0px');

            let status = 'PASS';
            if (ratio < required && text.length > 3) {
                status = 'FAIL';
            }

            if (status !== 'PASS') pass = false;
            checks.push({
                text, tag: el.tagName, inCard, color, bgColor: computedBg,
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
    print(f"  {report['total']} slides | {passed} PASS \u2705 | {failed} FAIL \u274c")
    print(f"{'='*60}\n")
    for s in report["slides"]:
        icon = "\u2705" if s["pass"] else "\u274c"
        bg = "BG" if s["hasBg"] else ("DARK" if s["hasDarkBg"] else "theme")
        print(f"  {icon} Slide {s['slide']:>2} [{bg:>5}] [{s['layout']:<14}]")
        for c in s["checks"]:
            if c["status"] != "PASS":
                loc = "[card]" if c["inCard"] else "[bg]"
                ratio = f" {c['ratio']}:1 (need {c['required']})"
                shad = "" if c["hasShadow"] else " NO-SHADOW"
                print(f"       <{c['tag']}> \"{c['text']}\"{loc} fg={c['color']}{ratio}{shad}")
        if s["pass"]:
            # Show first element's ratio as quick summary
            for c in s["checks"][:1]:
                loc = "[card]" if c["inCard"] else "[bg]"
                print(f"       \u2192 best: <{c['tag']}> {c['ratio']}:1 {loc}")
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
        print(f"  \ud83d\udcc4 Report saved: {args.json}")

    print_report(report)
    sys.exit(0 if report["pass"] else 1)

if __name__ == "__main__":
    main()
