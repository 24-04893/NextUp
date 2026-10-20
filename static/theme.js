/*
static/theme.js -- shared by EVERY page (bug A1 fix).

Why this exists: the dark-mode script used to live only inside
index.html, so /structures could never go dark and had
no toggle. One shared file fixes both at once.

How it decides:
  1. localStorage('nextup-theme') wins -- the user's explicit choice;
  2. otherwise the OS-level prefers-color-scheme;
  3. the toggle button (#theme-toggle) flips it and remembers.
*/
(function () {
    'use strict';
    // Defensive: ensure DOM elements exist before interacting
    const KEY = 'nextup-theme';
    const docEl = document.documentElement;
    const btn = document.getElementById('theme-toggle');
    // Guard: only proceed if toggle button exists
    if (!btn) return;

    // Helper: safely read localStorage (may throw in some contexts)
    const getStored = () => {
        try { return localStorage.getItem(KEY); } catch (e) { return null; }
    };
    const stored = getStored();
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;

    // Initialize theme: stored preference > OS preference > light default
    if (stored === 'dark' || (!stored && prefersDark)) {
        docEl.classList.add('theme-dark');
    }

    btn.addEventListener('click', function () {
        // Toggle dark mode
        const dark = docEl.classList.toggle('theme-dark');
        // Persist preference; guard setItem
        try { localStorage.setItem(KEY, dark ? 'dark' : 'light'); } catch (e) {}
        // 150ms color transition on bg/border/text during theme switches
        const animOn = !docEl.hasAttribute('data-anim') || docEl.getAttribute('data-anim') !== 'off';
        if (animOn) docEl.classList.add('color-slide');
        if (animOn) setTimeout(() => docEl.classList.remove('color-slide'), 260);
    });

    // keyboard+a11y: it is an <a role=button>, so Enter/Space works
    btn.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            btn.click();
        }
    });
})();
