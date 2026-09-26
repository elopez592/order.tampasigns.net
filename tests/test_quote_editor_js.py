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


def test_aframe_uses_quantity_and_frame_checkbox():
    source = Path('app/static/app.js').read_text(encoding='utf-8')
    assert "product?.name==='A-Frame inserts'" in source
    assert "Choose vehicle count" in source
    assert "${quantityHeading(product,cfg)}" in source
    assert 'name="add_frame"' in source
    assert "f.elements.add_frame?.checked?'with_frame'" in source
