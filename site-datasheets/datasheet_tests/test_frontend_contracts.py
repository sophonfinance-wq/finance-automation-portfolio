"""CSS/JS contracts for the progressive datasheet interactions."""
from __future__ import annotations

import re
from pathlib import Path

PARTIALS = Path(__file__).resolve().parents[1] / "partials"
CSS = (PARTIALS / "page.css").read_text(encoding="utf-8")
JS = (PARTIALS / "page.js").read_text(encoding="utf-8")


def test_die_stack_hero_is_the_contained_isometric_svg_with_interactive_cards():
    """The dimensional view is the layout-reserving isometric SVG (see test_die_stack.py);
    interaction is a flat, contained card list. The old free-floating CSS-3D stack
    overflowed its box and overlapped the panel, so it must not come back."""
    # Isometric SVG hero is present and sized to the content column.
    assert ".die-svg{" in CSS
    assert "max-width:540px" in CSS
    # Interactive layer cards are revealed only once JS is active, and are full-width
    # (they flow normally, so they cannot overlap the panel below).
    assert ".die-3d{display:none}" in CSS
    assert ".js-die .die-3d{display:flex;flex-direction:column" in CSS
    assert ".die-face{" in CSS and "cursor:pointer" in CSS
    assert ".die-face:focus-visible{" in CSS and "outline:4px solid #f1c21b" in CSS
    assert "document.documentElement.classList.add('js-die')" in JS
    # Guard against regressing to the overflowing 3-D transform.
    assert "perspective:1200px" not in CSS
    assert "translate3d(0,calc(var(--layer-y)" not in CSS
    assert "--layer-z" not in CSS
    assert "DRAG_THRESHOLD" not in JS


def test_buttons_support_click_keyboard_and_full_escape_reset():
    assert "btn.addEventListener('click'" in JS
    assert "e.key==='Enter'||e.key===' '" in JS
    assert "e.key==='Escape'" in JS
    assert "function clearSelection()" in JS
    assert "setUnpressed();" in JS
    assert "btn.setAttribute('aria-expanded','true')" in JS
    assert "face.setAttribute('aria-expanded','false')" in JS
    assert "panel.innerHTML=promptMarkup" in JS
    assert "if(focusWasInPanel&&returnFocus)returnFocus.focus()" in JS


def test_reduced_motion_keeps_static_details_and_never_swaps_video():
    # The video swap bails out entirely under reduced motion, before scanning any image.
    motion_guard = JS.index("if(motionQuery&&motionQuery.matches)return;")
    image_scan = JS.index("document.querySelectorAll('img[data-video]')")
    assert motion_guard < image_scan
    # Layer detail is plain click/keyboard wiring — it does not depend on motion or pointer drag.
    assert "btn.addEventListener('click'" in JS
    assert "document.documentElement.classList.add('js-die')" in JS
    # Reduced motion neutralizes all animation/transition (so the card hover lift is inert too).
    assert re.search(r"@media \(prefers-reduced-motion:reduce\)\{\*\{animation:none!important;transition:none!important\}", CSS)
    assert ".motion-media>img{display:block!important}" in CSS
    assert ".motion-media>video{display:none!important}" in CSS


def test_motion_video_has_controls_and_preserves_its_poster_for_print():
    assert "v.controls=true" in JS
    assert "v.setAttribute('controls','')" in JS
    assert "media.appendChild(img);media.appendChild(v)" in JS
    assert "function syncMotion(e){if(e.matches){v.pause();}" in JS
    assert "motionQuery.addEventListener('change',syncMotion)" in JS
    assert "@media print" in CSS
    assert "header.nav,.cta,.masthead .btn,.copybtn{display:none}" in CSS
    assert ".motion-media>img{display:block!important}" in CSS
    assert ".motion-media>video{display:none!important}" in CSS


def test_panel_content_uses_text_nodes_and_allows_only_github_https_links():
    assert "document.createTextNode(value||'')" in JS
    assert "heading.textContent=btn.textContent" in JS
    assert "url.protocol==='https:'&&url.hostname==='github.com'" in JS
    assert "panel.innerHTML='<" not in JS


def test_mobile_tables_scroll_locally_and_navigation_can_wrap():
    assert re.search(
        r"@media \(max-width:760px\).*?"
        r"table\.ds\{[^}]*display:block;[^}]*max-width:100%;"
        r"[^}]*overflow-x:auto;",
        CSS,
        re.DOTALL,
    )
    assert CSS.index("@media (max-width:760px)") > CSS.index(".die-face{")
    assert ".nav-in{flex-wrap:wrap" in CSS
    assert not re.search(r"html,body\{[^}]*overflow-x:(?:hidden|clip)", CSS)


def test_focus_and_print_runline_do_not_depend_on_screen_backgrounds():
    assert ":focus-visible{outline:3px solid var(--blue);outline-offset:3px}" in CSS
    assert ".die-face:focus-visible{" in CSS
    assert "outline:4px solid #f1c21b" in CSS
    assert re.search(
        r"@media print\{.*?\.verify \.runline\{"
        r"[^}]*background:#fff!important;[^}]*color:#000!important;"
        r"[^}]*border:1px solid #000;",
        CSS,
        re.DOTALL,
    )
