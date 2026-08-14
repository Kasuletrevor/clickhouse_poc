from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_JS = ROOT / "app/static/js/simulator_controller.js"


def test_cdc_gap_has_terminal_badge_close_action_and_gap_copy():
    js = CONTROLLER_JS.read_text(encoding="utf-8")
    assert '"cdc_gap"' in js
    assert "CDC GAP" in js
    assert "Close with CDC Gap" in js
    assert "/close-gap" in js
    assert "committed events were not recovered" in js
