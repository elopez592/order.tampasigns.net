from pathlib import Path


def test_quote_editor_row_renderer_is_defined_before_use():
    source = Path('app/static/app.js').read_text(encoding='utf-8')
    helper = source.find('function quoteRevisionRow')
    modal = source.find('function editQuoteModal')
    assert helper >= 0, 'quoteRevisionRow helper must exist for the Final charges modal'
    assert modal >= 0
    assert helper < modal
    assert 'quoteRevisionRow(line,i)' in source
    assert "data-action=\"add-quote-service\"" in source
