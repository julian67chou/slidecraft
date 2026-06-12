/**
 * SlideCraft Slider — runtime for slide navigation
 * 
 * Features:
 * - Keyboard: ← → ↑ ↓ Space Home End F S
 * - Mouse wheel / click on nav area
 * - Fullscreen (F key)
 * - Presenter mode (S key): notes + next slide preview + timer
 * - Slide counter + progress bar
 * - CSS transitions
 * - Touch/swipe support (mobile)
 * - Responsive fit (mobile + desktop)
 */
(function() {
  'use strict';

  const deck = document.querySelector('.deck');
  if (!deck) return;

  const wrappers = deck.querySelectorAll('.slide-wrapper');
  if (wrappers.length === 0) return;
  const slides = deck.querySelectorAll('section.slide');

  const SLIDE_W = 1280;
  const SLIDE_H = 720;

  let current = 0;
  let presenterWindow = null;
  let fullscreen = false;
  let touchStartX = 0;
  let touchStartY = 0;
  let touchStartTime = 0;
  let isMobile = false;
  let rafPending = false;

  // ── UI Elements ──────────────────────────────────────────────────

  const nav = document.createElement('div');
  nav.className = 'gamma-nav';
  nav.innerHTML = [
    '<div class="gamma-progress"><div class="gamma-progress-bar"></div></div>',
    '<div class="gamma-counter"></div>',
    '<div class="gamma-arrows">',
    '  <button class="gamma-arrow gamma-prev" title="Previous (←)">‹</button>',
    '  <button class="gamma-arrow gamma-next" title="Next (→)">›</button>',
    '</div>',
  ].join('');
  document.body.appendChild(nav);

  const progressBar = nav.querySelector('.gamma-progress-bar');
  const counter = nav.querySelector('.gamma-counter');

  // ── Responsive Fit ──────────────────────────────────────────────

  function fitSlides() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(function() {
      rafPending = false;
      var vw = window.innerWidth;
      var vh = window.innerHeight;
      isMobile = vw < 800;

      // On mobile: each wrapper fills viewport; slide fills wrapper
      // On desktop: scale to fit with padding
      var padX = isMobile ? 8 : 40;
      var padY = isMobile ? 0 : 100;
      var scaleX = (vw - padX) / SLIDE_W;
      var scaleY = (vh - padY) / SLIDE_H;
      var scale = Math.min(1, Math.max(0.25, Math.min(scaleX, scaleY)));

      // Apply scale to wrappers
      for (var i = 0; i < wrappers.length; i++) {
        wrappers[i].style.setProperty('--slide-scale', scale);
      }

      // On mobile: deck behaves like a viewport slider
      if (isMobile) {
        document.body.style.overflow = 'hidden';
        document.body.style.padding = '0';
        // Hide non-active wrappers on mobile (only show current)
        for (var j = 0; j < wrappers.length; j++) {
          wrappers[j].style.display = (j === current) ? 'flex' : 'none';
        }
        // Wrapper fills the screen
        var wrapperH = SLIDE_H * scale;
        var topOffset = Math.max(0, (vh - wrapperH) / 2);
        wrappers[current].style.marginTop = topOffset + 'px';
        // Show nav bar
        nav.style.bottom = '0';
      // Show one slide at a time (both mobile and desktop)
      document.body.style.overflow = 'hidden';
      document.body.style.padding = '0';
      // Only show current wrapper
      for (var j = 0; j < wrappers.length; j++) {
        wrappers[j].style.display = (j === current) ? 'flex' : 'none';
      }
      // Center the current slide
      var wrapperH = SLIDE_H * scale;
      var topOffset = Math.max(0, (vh - wrapperH) / 2);
      wrappers[current].style.marginTop = topOffset + 'px';
      // Show nav bar at bottom
      nav.style.bottom = '0';
    });
  }

  var resizeTimer = null;
  window.addEventListener('resize', function() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(fitSlides, 100);
  });

  // ── Navigation ───────────────────────────────────────────────────

  function goTo(index) {
    var target = Math.max(0, Math.min(index, slides.length - 1));
    if (target === current) return;
    
    slides[current].classList.remove('slide-active');
    slides[current].classList.add('slide-exit');
    
    slides[target].classList.remove('slide-exit');
    slides[target].classList.add('slide-active');
    current = target;
    updateUI();
    
    // Update which wrapper is visible (both mobile and desktop)
    for (var i = 0; i < wrappers.length; i++) {
      wrappers[i].style.display = (i === current) ? 'flex' : 'none';
    }
    // Re-center
    fitSlides();
  }

  function goNext() { goTo(current + 1); }
  function goPrev() { goTo(current - 1); }

  // ── UI Update ────────────────────────────────────────────────────

  function updateUI() {
    var pct = ((current + 1) / slides.length) * 100;
    progressBar.style.width = pct + '%';
    counter.textContent = (current + 1) + ' / ' + slides.length;

    if (presenterWindow && !presenterWindow.closed) {
      updatePresenter();
    }
  }

  // ── Keyboard ─────────────────────────────────────────────────────

  document.addEventListener('keydown', function(e) {
    if (e.target.closest('input, textarea, select, [contenteditable]')) return;

    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
      case ' ':
        e.preventDefault();
        goNext();
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault();
        goPrev();
        break;
      case 'Home':
        e.preventDefault();
        goTo(0);
        break;
      case 'End':
        e.preventDefault();
        goTo(slides.length - 1);
        break;
      case 'f':
      case 'F':
        e.preventDefault();
        toggleFullscreen();
        break;
      case 's':
      case 'S':
        e.preventDefault();
        togglePresenter();
        break;
    }
  });

  // ── Mouse Wheel ──────────────────────────────────────────────────

  var wheelTimeout = null;
  document.addEventListener('wheel', function(e) {
    if (!e.target.closest('.deck, .gamma-nav')) return;
    if (wheelTimeout) return;
    wheelTimeout = setTimeout(function() { wheelTimeout = null; }, 600);
    if (e.deltaY > 0 || e.deltaX > 0) goNext();
    else goPrev();
  }, { passive: true });

  // ── Touch / Swipe ───────────────────────────────────────────────

  document.addEventListener('touchstart', function(e) {
    touchStartX = e.changedTouches[0].screenX;
    touchStartY = e.changedTouches[0].screenY;
    touchStartTime = Date.now();
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    var dx = e.changedTouches[0].screenX - touchStartX;
    var dy = e.changedTouches[0].screenY - touchStartY;
    var absDx = Math.abs(dx);
    var absDy = Math.abs(dy);
    var dt = Date.now() - touchStartTime;
    
    // Tap: go next/prev based on which half was tapped
    if (absDx < 30 && absDy < 30 && dt < 300) {
      if (e.changedTouches[0].screenX < window.innerWidth * 0.4) {
        goPrev();
      } else if (e.changedTouches[0].screenX > window.innerWidth * 0.6) {
        goNext();
      }
      return;
    }
    
    // Swipe: horizontal only, min 40px
    if (absDx > 40 && absDx > absDy * 1.5) {
      if (dx < 0) goNext();
      else goPrev();
    }
  }, { passive: true });

  // ── Fullscreen ──────────────────────────────────────────────────

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(function() {});
      fullscreen = true;
    } else {
      document.exitFullscreen().catch(function() {});
      fullscreen = false;
      setTimeout(fitSlides, 200);
    }
  }

  // ── Presenter Mode ──────────────────────────────────────────────

  function togglePresenter() {
    if (presenterWindow && !presenterWindow.closed) {
      presenterWindow.close();
      presenterWindow = null;
      return;
    }
    presenterWindow = window.open('', 'gamma-presenter',
      'width=800,height=600,menubar=no,toolbar=no,location=no,status=no');
    if (presenterWindow) {
      presenterWindow.document.write(buildPresenterHTML());
      presenterWindow.document.close();
      updatePresenter();
    }
  }

  function buildPresenterHTML() {
    return '<!DOCTYPE html>\n<html><head><title>Gamma Presenter</title>\n<style>\n  * { margin: 0; padding: 0; box-sizing: border-box; }\n  body { font-family: system-ui, sans-serif; background: #1a1a1a; color: #eee; padding: 20px; }\n  .container { max-width: 700px; margin: 0 auto; }\n  h1 { font-size: 24px; margin-bottom: 10px; }\n  .timer { font-size: 40px; font-weight: 300; margin-bottom: 20px; font-variant-numeric: tabular-nums; }\n  .current-slide { background: #2a2a2a; border-radius: 8px; padding: 20px; margin-bottom: 16px; }\n  .current-slide h2 { font-size: 18px; color: #888; margin-bottom: 8px; }\n  .current-slide .content { font-size: 24px; line-height: 1.5; }\n  .notes { background: #333; border-radius: 8px; padding: 16px; margin-bottom: 16px; }\n  .notes h2 { font-size: 14px; color: #888; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 1px; }\n  .notes .text { font-size: 18px; line-height: 1.6; color: #ddd; }\n  .next-preview { background: #222; border-radius: 8px; padding: 16px; opacity: 0.7; }\n  .next-preview h2 { font-size: 14px; color: #888; margin-bottom: 6px; text-transform: uppercase; }\n  .next-preview .content { font-size: 16px; color: #aaa; }\n  #start-btn { position: fixed; top: 20px; right: 20px; background: #6C5CE7; color: #fff; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }\n  #start-btn:hover { background: #5A4BD1; }\n</style></head>\n<body>\n<div class="container">\n  <h1>🎤 Gamma Presenter</h1>\n  <div class="timer" id="timer">00:00</div>\n  <button id="start-btn" onclick="startTimer()">Start Timer</button>\n  <div class="current-slide">\n    <h2>Current Slide</h2>\n    <div class="content" id="current-content">—</div>\n  </div>\n  <div class="notes">\n    <h2>Speaker Notes</h2>\n    <div class="text" id="notes-text">No notes for this slide.</div>\n  </div>\n  <div class="next-preview">\n    <h2>Up Next</h2>\n    <div class="content" id="next-content">—</div>\n  </div>\n</div>\n<'+'script>\n  var startTime = null;\n  var timerInterval = null;\n  function startTimer() {\n    if (timerInterval) return;\n    startTime = Date.now();\n    timerInterval = setInterval(function() {\n      var elapsed = Math.floor((Date.now() - startTime) / 1000);\n      var m = String(Math.floor(elapsed / 60)).padStart(2, "0");\n      var s = String(elapsed % 60).padStart(2, "0");\n      document.getElementById("timer").textContent = m + ":" + s;\n    }, 500);\n  }\n  window.addEventListener("message", function(e) {\n    var d = e.data;\n    if (d.type === "slide-update") {\n      document.getElementById("current-content").textContent = d.currentTitle || "(No title)";\n      document.getElementById("notes-text").textContent = d.notes || "(No notes)";\n      document.getElementById("next-content").textContent = d.nextTitle || "(End of presentation)";\n    }\n  });\n<'+'/script>\n</body></html>';
  }

  function updatePresenter() {
    if (!presenterWindow || presenterWindow.closed) return;
    var slide = slides[current];
    var nextSlide = slides[current + 1];
    var notesEl = slide.querySelector('.notes');
    
    presenterWindow.postMessage({
      type: 'slide-update',
      currentTitle: (slide.querySelector('h1, h2') || {}).textContent || '(No title)',
      notes: (notesEl ? notesEl.textContent : '') || '(No notes)',
      nextTitle: (nextSlide ? nextSlide.querySelector('h1, h2') || {} : {}).textContent || '(End of presentation)'
    }, '*');
  }

  // ── Init ─────────────────────────────────────────────────────────

  // Mark first slide as active
  for (var i = 0; i < slides.length; i++) {
    if (i === 0) slides[i].classList.add('slide-active');
    else slides[i].classList.remove('slide-active');
  }

  fitSlides();
  updateUI();

  // Arrow button listeners
  nav.querySelector('.gamma-prev').addEventListener('click', function(e) {
    e.stopPropagation();
    goPrev();
  });
  nav.querySelector('.gamma-next').addEventListener('click', function(e) {
    e.stopPropagation();
    goNext();
  });

  // ── Slider Styles (injected) ─────────────────────────────────────

  var styleEl = document.createElement('style');
  styleEl.textContent = [
    '/* Gamma Nav */',
    '.gamma-nav {',
    '  position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000;',
    '  pointer-events: none;',
    '}',
    '.gamma-nav * { pointer-events: auto; }',
    '.gamma-progress {',
    '  position: fixed; top: 0; left: 0; right: 0; height: 3px;',
    '  background: rgba(255,255,255,0.1); z-index: 1001;',
    '}',
    '.gamma-progress-bar {',
    '  height: 100%;',
    '  background: linear-gradient(90deg, var(--accent, #6C5CE7), var(--accent2, #00D2D3));',
    '  transition: width 0.3s ease; width: 0%;',
    '}',
    '.gamma-counter {',
    '  position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);',
    '  font-size: 13px; color: rgba(255,255,255,0.5);',
    '  font-family: system-ui, sans-serif; letter-spacing: 1px;',
    '  background: rgba(0,0,0,0.4); padding: 4px 14px;',
    '  border-radius: 12px; backdrop-filter: blur(4px);',
    '  white-space: nowrap; z-index: 1002;',
    '}',
    '.gamma-arrows {',
    '  position: fixed; bottom: 16px; right: 16px;',
    '  display: flex; gap: 8px; z-index: 1002;',
    '}',
    '.gamma-arrow {',
    '  width: 44px; height: 44px; border-radius: 50%; border: none;',
    '  background: rgba(0,0,0,0.45); color: #fff; cursor: pointer;',
    '  font-size: 24px; display: flex; align-items: center; justify-content: center;',
    '  backdrop-filter: blur(4px); transition: background 0.2s;',
    '  -webkit-tap-highlight-color: transparent;',
    '}',
    '.gamma-arrow:hover { background: rgba(0,0,0,0.6); }',
    '.gamma-arrow:active { transform: scale(0.88); }',
    '',
    '/* Slide Wrapper — handles responsive scaling */',
    '.slide-wrapper {',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  width: 100%;',
    '  flex-shrink: 0;',
    '}',
    '.slide-wrapper section.slide {',
    '  transform-origin: center center;',
    '  transform: scale(var(--slide-scale, 1));',
    '  transition: opacity 0.4s ease;',
    '}',
    '.slide-wrapper section.slide:not(.slide-active) {',
    '  opacity: 0.15;',
    '}',
    '.slide-wrapper section.slide.slide-active {',
    '  opacity: 1;',
    '}',
    '.slide-wrapper section.slide.slide-exit {',
    '  opacity: 0;',
    '}',
    '',
    '/* Mobile: fullscreen slides */',
    '@media (max-width: 800px) {',
    '  .gamma-counter { bottom: 14px; font-size: 12px; padding: 3px 12px; }',
    '  .gamma-arrows { bottom: 10px; right: 10px; gap: 10px; }',
    '  .gamma-arrow { width: 48px; height: 48px; font-size: 26px; }',
    '  .gamma-progress { height: 2px; }',
    '}',
    '',
    '/* Fullscreen */',
    ':-webkit-full-screen .slide-wrapper section.slide {',
    '  box-shadow: none; border: none;',
    '}',
    ':fullscreen .slide-wrapper section.slide {',
    '  box-shadow: none; border: none;',
    '}',
  ].join('\n');
  document.head.appendChild(styleEl);

  console.log('SlideCraft Slider loaded. ← → arrows, Home/End, F=fullscreen, S=presenter');

  // ── Orientation Change ──────────────────────────────────────────
  // On mobile, re-fit when screen rotates
  if ('orientation' in window) {
    window.addEventListener('orientationchange', function() {
      setTimeout(fitSlides, 300);
    });
  }
})();
