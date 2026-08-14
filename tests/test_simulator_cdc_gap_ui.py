from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIMULATOR_JS = ROOT / "app/static/js/simulator.js"


def test_cdc_gap_has_terminal_badge_close_action_and_gap_copy():
    js = SIMULATOR_JS.read_text(encoding="utf-8")
    assert 'cdc_gap: ["CDC GAP"' in js
    assert "Close with CDC Gap" in js
    assert "/close-gap" in js
    assert "committed events were not recovered" in js
