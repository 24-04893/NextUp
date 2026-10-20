/*
static/motion.js -- shared motion and animation helpers.

Owns:
  * the "Anim: on / off" header toggle (remembered in localStorage under
    nextup.anim), defaulting to the OS prefers-reduced-motion value
  * window.__animOn() so other scripts can skip JS-driven motion
  * the staggered page-load slam (transform/opacity only, capped at 20)
  * the --i stagger indices for week bars and heap-array slots
Everything else (rows, toasts, trees) lives in the page's own script.
No animation library; instant states when motion is off.
*/
(function () {
    'use strict';

    var root = document.documentElement;
    var KEY = 'nextup.anim';
    var mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

    function userChoice() {
        try { return localStorage.getItem(KEY); } catch (e) { return null; }
    }
    function effective() {
        var u = userChoice();
        if (u) return u;                       // explicit user choice wins
        return (mq && mq.matches) ? 'off' : 'on';
    }
    function apply() {
        var v = effective();
        root.setAttribute('data-anim', v);
        var link = document.getElementById('anim-toggle');
        if (link) link.textContent = 'Animations: ' + (v === 'off' ? 'Off' : 'On');
    }
    apply();
    window.__animOn = function () { return root.getAttribute('data-anim') !== 'off'; };
    if (mq && mq.addEventListener) mq.addEventListener('change', apply);

    function onceClass(el, cls, index, cap) {
        // Defensive: only proceed if element exists and is connected to DOM
        if (!el || !el.isConnected) return;
        if (index !== undefined) {
            var idx = Number(index);
            if (!isNaN(idx)) el.style.setProperty('--i', String(Math.min(idx, cap)));
        }
        el.classList.add(cls);
        // Only add animationend listener if element is in DOM
        if (el.isConnected) {
            el.addEventListener('animationend', function () {
                el.classList.remove(cls);
                el.style.removeProperty('--i');
            }, { once: true });
        }
    }

    window.addEventListener('DOMContentLoaded', function () {
        // Defensive: only proceed if root exists
        if (!root) return;
        var link = document.getElementById('anim-toggle');
        if (link) {
            link.addEventListener('click', function (ev) {
                ev.preventDefault();
                var cur = userChoice() || effective();
                try { localStorage.setItem(KEY, cur === 'off' ? 'on' : 'off'); } catch (e) {}
                apply();
            });
            // keyboard+a11y: it is an <a role=button>, so Enter/Space works
            link.addEventListener('keydown', function (ev) {
                if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault();
                    link.click();
                }
            });
        }
        // Only apply animations if animations are enabled
        if (!window.__animOn()) return;

        // staggered slam for the meaningful blocks (capped at 20)
        var blocks = document.querySelectorAll('.hero, .sheet .section, .sidebar .panel');
        // Guard: only iterate if blocks is a valid NodeList
        if (blocks && blocks.length > 0) {
            for (var i = 0; i < blocks.length && i < 20; i++) {
                onceClass(blocks[i], 'slammat', i, 19);
            }
        }
        // week-strip day cards: --i drives the bar-grow stagger
        var days = document.querySelectorAll('.week-day');
        if (days && days.length > 0) {
            for (var d = 0; d < days.length; d++) {
                days[d].style.setProperty('--i', String(Math.min(d, 19)));
            }
        }
        // heap array slots pop-in stagger (only the first 20 stagger)
        var slots = document.querySelectorAll('.array-slot');
        if (slots && slots.length > 0) {
            for (var s = 0; s < slots.length && s < 20; s++) {
                slots[s].style.setProperty('--i', String(s));
            }
        }
    });
})();
