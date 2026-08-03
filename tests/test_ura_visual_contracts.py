from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "app/static/css/app.css"
DASHBOARD_JS_PATH = ROOT / "app/static/js/dashboard.js"


def css_text():
    return CSS_PATH.read_text()


def compact(value: str) -> str:
    return "".join(value.split()).lower()


def test_ura_brand_tokens_are_source_of_truth():
    css = compact(css_text())

    assert "--ura-blue:#1850a1" in css
    assert "--ura-blue-2:#5287c1" in css
    assert "--ura-yellow:#fdf22c" in css
    assert "--ura-yellow-soft:#fcf59a" in css
    assert "--ura-yellow-hover:#f0e964" in css
    assert "--ura-surface:#e2e9f0" in css
    assert "--ura-blue-soft:#b1c6e0" in css
    assert "--text:#212529" in css
    assert "--muted:#4b4c4d" in css


def test_gotham_first_font_stack_has_system_fallbacks_without_font_face():
    css = css_text()
    normalized = compact(css)

    assert 'font-family:"gotham-book",system-ui,-apple-system,"segoeui",arial,helvetica,sans-serif' in normalized
    assert "@font-face" not in normalized


def test_sidebar_and_active_navigation_use_ura_identity():
    css = compact(css_text())

    assert ".sidebar{background:var(--ura-blue)" in css
    assert ".nav-item.active{background:var(--ura-yellow);color:var(--text)" in css


def test_primary_and_secondary_actions_use_brand_colours():
    css = compact(css_text())

    assert ".btn{border:1pxsolidvar(--ura-blue);background:#fff" in css
    assert ".btn-primary{background:var(--ura-yellow);border-color:var(--ura-yellow);color:var(--text)" in css
    assert ".btn-primary:hover{background:var(--ura-yellow-hover);border-color:var(--ura-yellow-hover)" in css


def test_semantic_actions_remain_separate_from_brand_colours():
    css = compact(css_text())

    assert "--success:#15803d" in css
    assert "--warning:#b45309" in css
    assert "--danger:#b91c1c" in css
    assert ".btn-success{color:#fff;background:var(--success)" in css
    assert ".btn-danger" in css and "var(--danger)" in css


def test_forms_tables_and_detail_tiles_use_blue_grey_system():
    css = compact(css_text())

    assert ".input:focus,.select:focus{border-color:var(--ura-blue-2)" in css
    assert "th{background:var(--table-head)" in css
    assert "tr:hovertd{background:var(--row-hover)" in css
    assert ".detail{padding:13px;background:var(--detail-bg)" in css


def test_dashboard_uses_ura_brand_for_structure_but_semantic_status_colours():
    css = compact(css_text())
    js = DASHBOARD_JS_PATH.read_text()

    assert ".dashboard-kpi-money{background:var(--ura-blue)" in css
    assert ".dashboard-bar{fill:var(--ura-blue)" in css
    assert ".dashboard-bar-primary{fill:var(--ura-yellow)" in css
    assert ".donut-successful{stroke:var(--success)" in css
    assert ".donut-pending{stroke:var(--warning)" in css
    assert ".donut-reversed{stroke:var(--danger)" in css
    assert 'index === 0 ? "dashboard-bar dashboard-bar-primary" : "dashboard-bar"' in js


def test_focus_and_disabled_states_are_visible():
    css = compact(css_text())

    assert ":focus-visible" in css
    assert "outline:3pxsolidvar(--focus-ring)" in css
    assert ".btn:disabled" in css
    assert "cursor:not-allowed" in css
