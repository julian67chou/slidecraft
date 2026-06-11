/**
 * Gamma PPT Slider — runtime for slide navigation
 * 
 * Features:
 * - Keyboard: ← → ↑ ↓ Space Home End F S
 * - Mouse wheel / click on nav area
 * - Fullscreen (F key)
 * - Presenter mode (S key): notes + next slide preview + timer
 * - Slide counter + progress bar
 * - CSS transitions
 * - Touch/swipe support
 */
(function() {
  'use strict';

  const deck = document.querySelector('.deck');
  if (!deck) return;

  const slides = deck.querySelectorAll('section.slide');
  if (slides.length === 0) return;

  let current = 0;
  let presenterWindow = null;
  let fullscreen = false;
  let touchStartX = 0;
  let touchStartY = 0;

  // ── UI Elements ──────────────────────────────────────────────────

  // Navigation overlay
  const nav = document.createElement('div');
  nav.className = 'gamma-nav';
  nav.innerHTML = `
    <div class="gamma-progress"><div class="gamma-progress-bar"></div></div>
    <div class="gamma-counter"></div>
    <div class="gamma-arrows">
      <button class="gamma-arrow gamma-prev" title="Previous (←)">‹</button>
      <button class="gamma-arrow gamma-next" title="Next (→)">›</button>
    </div>
  `;
  document.body.appendChild(nav);

  const progressBar = nav.querySelector('.gamma-progress-bar');
  const counter = nav.querySelector('.gamma-counter');

  // Click on nav edges to navigate
  document.addEventListener('click', function(e) {
    // Don't intercept clicks on interactive elements
    if (e.target.closest('button, a, input, textarea, select, .gamma-nav')) return;
    const rect = document.body.getBoundingClientRect();
    if (e.clientX < rect.width * 0.4) goPrev();
    else if (e.clientX > rect.width * 0.6) goNext();
  });

  // ── Navigation ───────────────────────────────────────────────────

  function goTo(index) {
    const target = Math.max(0, Math.min(index, slides.length - 1));
    if (target === current) return;
    // Remove active from current
    slides[current].classList.remove('slide-active');
    slides[current].classList.add('slide-exit');
    // Activate target
    slides[target].classList.remove('slide-exit');
    slides[target].classList.add('slide-active');
    current = target;
    updateUI();
    // Scroll into view (for non-fullscreen mode)
    slides[current].scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function goNext() { goTo(current + 1); }
  function goPrev() { goTo(current - 1); }

  // ── UI Update ────────────────────────────────────────────────────

  function updateUI() {
    const pct = ((current + 1) / slides.length) * 100;
    progressBar.style.width = pct + '%';
    counter.textContent = (current + 1) + ' / ' + slides.length;

    // Update presenter window
    if (presenterWindow && !presenterWindow.closed) {
      updatePresenter();
    }
  }

  // ── Keyboard ─────────────────────────────────────────────────────

  document.addEventListener('keydown', function(e) {
    // Ignore if typing in an input
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

  let wheelTimeout = null;
  document.addEventListener('wheel', function(e) {
    // Only if over the deck area
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
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    const dx = e.changedTouches[0].screenX - touchStartX;
    const dy = e.changedTouches[0].screenY - touchStartY;
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);
    // Only horizontal swipes, min 50px
    if (absDx > 50 && absDx > absDy * 1.5) {
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
    const now = new Date();
    return `<!DOCTYPE html>
<html><head><title>Gamma Presenter</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: #1a1a1a; color: #eee; padding: 20px; }
  .container { max-width: 700px; margin: 0 auto; }
  h1 { font-size: 24px; margin-bottom: 10px; }
  .timer { font-size: 40px; font-weight: 300; margin-bottom: 20px; font-variant-numeric: tabular-nums; }
  .current-slide { background: #2a2a2a; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
  .current-slide h2 { font-size: 18px; color: #888; margin-bottom: 8px; }
  .current-slide .content { font-size: 24px; line-height: 1.5; }
  .notes { background: #333; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .notes h2 { font-size: 14px; color: #888; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 1px; }
  .notes .text { font-size: 18px; line-height: 1.6; color: #ddd; }
  .next-preview { background: #222; border-radius: 8px; padding: 16px; opacity: 0.7; }
  .next-preview h2 { font-size: 14px; color: #888; margin-bottom: 6px; text-transform: uppercase; }
  .next-preview .content { font-size: 16px; color: #aaa; }
  #start-btn { position: fixed; top: 20px; right: 20px; background: #6C5CE7; color: #fff; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }
  #start-btn:hover { background: #5A4BD1; }
</style></head>
<body>
<div class="container">
  <h1>🎤 Gamma Presenter</h1>
  <div class="timer" id="timer">00:00</div>
  <button id="start-btn" onclick="startTimer()">Start Timer</button>
  <div class="current-slide">
    <h2>Current Slide</h2>
    <div class="content" id="current-content">—</div>
  </div>
  <div class="notes">
    <h2>Speaker Notes</h2>
    <div class="text" id="notes-text">No notes for this slide.</div>
  </div>
  <div class="next-preview">
    <h2>Up Next</h2>
    <div class="content" id="next-content">—</div>
  </div>
</div>
<script>
  var startTime = null;
  var timerInterval = null;
  function startTimer() {
    if (timerInterval) return;
    startTime = Date.now();
    timerInterval = setInterval(function() {
      var elapsed = Math.floor((Date.now() - startTime) / 1000);
      var m = String(Math.floor(elapsed / 60)).padStart(2, '0');
      var s = String(elapsed % 60).padStart(2, '0');
      document.getElementById('timer').textContent = m + ':' + s;
    }, 500);
  }
  // Listen for updates from opener
  window.addEventListener('message', function(e) {
    var d = e.data;
    if (d.type === 'slide-update') {
      document.getElementById('current-content').textContent = d.currentTitle || '(No title)';
      document.getElementById('notes-text').textContent = d.notes || '(No notes)';
      document.getElementById('next-content').textContent = d.nextTitle || '(End of presentation)';
    }
  });
</script>
</body></html>`;
  }

  function updatePresenter() {
    if (!presenterWindow || presenterWindow.closed) return;
    const slide = slides[current];
    const nextSlide = slides[current + 1];
    const notesEl = slide.querySelector('.notes');
    
    presenterWindow.postMessage({
      type: 'slide-update',
      currentTitle: slide.querySelector('h1, h2')?.textContent?.trim() || '(No title)',
      notes: notesEl?.textContent?.trim() || '(No notes)',
      nextTitle: nextSlide?.querySelector('h1, h2')?.textContent?.trim() || '(End of presentation)'
    }, '*');
  }

  // ── Init ─────────────────────────────────────────────────────────

  // Mark first slide as active
  slides.forEach(function(s, i) {
    if (i === 0) s.classList.add('slide-active');
    else s.classList.remove('slide-active');
  });

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

  const style = document.createElement('style');
  style.textContent = `
    .gamma-nav {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 1000;
      pointer-events: none;
    }
    .gamma-nav * {
      pointer-events: auto;
    }
    .gamma-progress {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: rgba(255,255,255,0.1);
      z-index: 1001;
    }
    .gamma-progress-bar {
      height: 100%;
      background: linear-gradient(90deg, var(--accent, #6C5CE7), var(--accent2, #00D2D3));
      transition: width 0.3s ease;
      width: 0%;
    }
    .gamma-counter {
      position: fixed;
      bottom: 16px;
      left: 50%;
      transform: translateX(-50%);
      font-size: 13px;
      color: rgba(255,255,255,0.5);
      font-family: system-ui, sans-serif;
      letter-spacing: 1px;
      background: rgba(0,0,0,0.4);
      padding: 4px 14px;
      border-radius: 12px;
      backdrop-filter: blur(4px);
    }
    .gamma-arrows {
      position: fixed;
      bottom: 16px;
      right: 16px;
      display: flex;
      gap: 6px;
    }
    .gamma-arrow {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      border: none;
      background: rgba(0,0,0,0.4);
      color: #fff;
      font-size: 20px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      backdrop-filter: blur(4px);
      transition: background 0.2s;
    }
    .gamma-arrow:hover {
      background: rgba(0,0,0,0.6);
    }
    .gamma-arrow:active {
      transform: scale(0.92);
    }

    /* Slide transitions */
    section.slide {
      transition: opacity 0.4s ease, transform 0.4s ease;
    }
    section.slide:not(.slide-active) {
      opacity: 0.3;
      transform: scale(0.97);
    }
    section.slide.slide-active {
      opacity: 1;
      transform: scale(1);
    }
    section.slide.slide-exit {
      opacity: 0;
      transform: scale(0.95);
    }

    /* Fullscreen adjustments */
    :-webkit-full-screen .deck {
      justify-content: center;
    }
    :-webkit-full-screen section.slide {
      box-shadow: none;
      border: none;
    }
    :fullscreen .deck {
      justify-content: center;
    }
    :fullscreen section.slide {
      box-shadow: none;
      border: none;
    }
  `;
  document.head.appendChild(style);

  console.log('Gamma PPT Slider loaded. Navigation: ← → arrows, Home/End, F=fullscreen, S=presenter mode');
})();
