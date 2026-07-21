"""CSS/JS contracts for the progressive datasheet interactions."""
from __future__ import annotations

import re
from pathlib import Path

PARTIALS = Path(__file__).resolve().parents[1] / "partials"
CSS = (PARTIALS / "page.css").read_text(encoding="utf-8")
JS = (PARTIALS / "page.js").read_text(encoding="utf-8")


def test_die_stack_is_exploded_and_actually_three_dimensional():
    """Do not let a flat vertical button list masquerade as the 3-D view."""
    assert "perspective:1200px" in CSS
    assert "transform-style:preserve-3d" in CSS
    assert re.search(
        r"transform:rotateX\(var\(--die-rotate-x,\s*62deg\)\)\s*"
        r"rotateZ\(var\(--die-rotate-z,\s*-28deg\)\)",
        CSS,
    )
    assert "transform:translate3d(" in CSS
    assert ".die-3d{" in CSS and "pointer-events:none" in CSS
    assert ".die-face{" in CSS and "pointer-events:auto" in CSS

    depths = re.findall(
        r"\.die-face:nth-child\(\d\)\{[^}]*--layer-z:(-?\d+)px", CSS
    )
    assert len(depths) == 5
    assert len(set(depths)) == 5
    assert ".js-3d .die-3d{display:grid}" in CSS


def test_pointer_drag_has_a_threshold_bounds_and_click_suppression():
    for event in ("pointerdown", "pointermove", "pointerup", "pointercancel"):
        assert f"addEventListener('{event}'" in JS
    threshold = re.search(r"var DRAG_THRESHOLD=(\d+)", JS)
    assert threshold and int(threshold.group(1)) >= 5
    threshold_guard = JS.index("Math.hypot(dx,dy)<DRAG_THRESHOLD")
    pointer_capture = JS.index("setPointerCapture(pointerId)")
    assert threshold_guard < pointer_capture
    assert "setPointerCapture" in JS
    assert "releasePointerCapture" in JS
    assert "Date.now()<suppressClickUntil" in JS
    assert "suppressClickUntil=Date.now()+300" in JS
    assert "clamp(startRotateX-dy*.12,55,70)" in JS
    assert "clamp(startRotateZ+dx*.18,-35,35)" in JS
    assert "--die-rotate-x" in JS and "--die-rotate-z" in JS


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
    motion_guard = JS.index("if(motionQuery&&motionQuery.matches)return;")
    image_scan = JS.index("document.querySelectorAll('img[data-video]')")
    assert motion_guard < image_scan

    # Detail wiring happens before the reduced-motion return; pointer wiring after it.
    click_wiring = JS.index("btn.addEventListener('click'")
    static_return = JS.index("if(reduce)return;")
    pointer_wiring = JS.index("addEventListener('pointerdown'")
    assert click_wiring < static_return < pointer_wiring
    assert "reduce?'js-static':'js-3d'" in JS
    assert "window.matchMedia&&window.matchMedia('print')" in JS
    assert "query.addEventListener('change',syncInstruction)" in JS
    assert ".js-static .die-3d{display:grid" in CSS
    assert ".js-static .die-face{grid-area:auto" in CSS
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
    assert CSS.index("@media (max-width:760px)") > CSS.index(".die-face{--layer-y:")
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
