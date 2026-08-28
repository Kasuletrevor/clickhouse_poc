from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "app/templates/index.html"
APP_JS = ROOT / "app/static/js/app.js"
PAGE_JS = ROOT / "app/static/js/payments_cdc_simulator.js"


def test_streaming_poc_is_a_separate_navigation_page():
    html = INDEX.read_text()
    app_js = APP_JS.read_text()

    assert 'data-page="streaming-poc"' in html
    assert "Streaming POC" in html
    assert 'from "./payments_cdc_simulator.js"' in app_js
    assert 'page==="streaming-poc"' in app_js


def test_payments_cdc_page_reuses_simulator_visual_language_for_the_payment_case():
    page = PAGE_JS.read_text()

    assert "Payments & Taxpayer CDC Simulator" in page
    assert "Oracle" in page
    assert "Debezium" in page
    assert "Kafka" in page
    assert "ClickHouse" in page
    assert "Payment transactions" in page
    assert "Taxpayer station changes" in page
    assert "EFRIS Simulator Control Room" not in page


def test_payments_cdc_page_is_wired_to_the_streaming_poc_backend():
    page = PAGE_JS.read_text()

    assert 'api("/api/streaming-poc/status")' in page
    assert 'api("/api/streaming-poc/start"' in page
    assert 'api("/api/streaming-poc/stop"' in page
