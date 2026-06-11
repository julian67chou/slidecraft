"""
Grok Draw integration — generate presentation images via Grok CLI.

Usage:
    from orchestrator.grok_draw import generate_image
    path = generate_image("Warm geometric background, beige tones, 16:9")
"""
import subprocess
import json
import re
import os
import time
from pathlib import Path
from urllib.parse import unquote


# Detect grok binary location
GROK_BIN = None
for candidate in [
    os.path.expanduser("~/.grok/bin/grok"),
    os.path.expanduser("~/.npm-global/bin/grok-build"),
]:
    p = Path(candidate)
    if p.exists():
        GROK_BIN = str(p)
        break

if GROK_BIN is None:
    # Try PATH
    import shutil
    GROK_BIN = shutil.which("grok") or shutil.which("grok-build") or "grok"


def generate_image(prompt: str, aspect: str = "16:9", timeout: int = 45) -> str:
    """
    Generate an image using Grok Draw.
    
    Args:
        prompt: Text description of the desired image
        aspect: Aspect ratio (default "16:9" for slides)
        timeout: Max seconds to wait
    
    Returns:
        Absolute path to the generated image file
    
    Raises:
        RuntimeError: If image generation fails or path not found
    """
    full_prompt = f"Generate a {aspect} image for a presentation slide: {prompt.strip()}. Output the image file path."
    
    result = subprocess.run(
        [GROK_BIN, "-p", full_prompt, "--always-approve"],
        capture_output=True, text=True, timeout=timeout
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Grok Draw failed (exit {result.returncode}): {result.stderr[:500]}")
    
    output = result.stdout + result.stderr
    
    # Extract image path — Grok returns a path like:
    # /home/hermeswebui/.grok/sessions/%2Fworkspace%2F.../images/1.jpg
    # The filesystem stores the URL-encoded form literally
    path_patterns = [
        r'(/home/[^\s]+/\.grok/sessions/[^\s]+?/images/\d+\.\w+)',
        r'(/tmp/[^\s]+\.\w+)',
    ]
    
    for pattern in path_patterns:
        # First try the raw (URL-encoded) match
        match = re.search(pattern, output)
        if match:
            path = match.group(1)
            if os.path.exists(path):
                return path
        
        # Then try URL-decoded form
        decoded_output = unquote(output)
        match = re.search(pattern, decoded_output)
        if match:
            path = match.group(1)
            # Check both the raw decoded path and reconstruct the URL-encoded form
            if os.path.exists(path):
                return path
            # Filesystem might store the %-encoded form even though we decoded the output
            # Reconstruct: encode / back to %2F in the relevant section
            encoded_path = path.replace('/.grok/sessions/', '/.grok/sessions/%2F', 1)
            if os.path.exists(encoded_path):
                return encoded_path
    
    # Fallback: look for most recent image in grok sessions
    grok_images_dir = Path.home() / ".grok" / "sessions"
    if grok_images_dir.exists():
        # Find newest image across all sessions
        newest = None
        newest_time = 0
        for session_dir in grok_images_dir.iterdir():
            img_dir = session_dir / "images"
            if img_dir.is_dir():
                for img in img_dir.glob("*.*"):
                    if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                        mtime = img.stat().st_mtime
                        if mtime > newest_time:
                            newest = str(img)
                            newest_time = mtime
        # Fallback: try relative path from cwd
        if not newest:
            cwd = Path.cwd()
            m2 = re.search(r'[\'"`]([^\'\"`]+\.(jpg|jpeg|png|webp))[\'"`]', output)
            if m2:
                rel = m2.group(1)
                candidates = [cwd / rel, cwd / "output" / rel, Path(rel)]
                for c in candidates:
                    if c.exists():
                        newest = str(c)
                        newest_time = c.stat().st_mtime
                        break

        if newest:
            return newest
    
    raise RuntimeError(
        f"Could not find generated image path.\n"
        f"Grok output:\n{output[:1000]}"
    )


def generate_background(prompt: str, theme_colors: dict = None) -> str:
    """
    Generate a slide background image with optional theme color reference.
    
    Args:
        prompt: Background description
        theme_colors: Dict with 'accent', 'bg' hex colors for style consistency
    
    Returns:
        Path to generated image
    """
    color_hint = ""
    if theme_colors:
        accent = theme_colors.get("accent", "")
        bg = theme_colors.get("bg", "")
        if accent and bg:
            color_hint = f" Color palette: background {bg}, accent {accent}. "
    
    full = f"{prompt.strip()}{color_hint}Minimalist, professional, 16:9, suitable for text overlay."
    return generate_image(full)


def generate_illustration(prompt: str, style: str = "flat vector") -> str:
    """
    Generate a slide illustration (icon, diagram, or graphic).
    
    Args:
        prompt: What to illustrate
        style: Art style (flat vector, watercolor, line art, etc.)
    
    Returns:
        Path to generated image
    """
    full = f"{prompt.strip()}. Style: {style}. Clean, professional."
    return generate_image(full, aspect="1:1")
