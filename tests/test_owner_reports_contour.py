def test_contour_generator_is_enabled_for_cut_stickers_and_decals(env):
    app, admin, employee = env
    catalog = admin.get('/api/catalog').json()['products']
    products = {product['name']: product for product in catalog}
    assert products['Die-cut stickers']['config']['contour_customizer'] is True
    assert products['Decals']['config']['contour_customizer'] is True
    assert products['Banners']['config']['contour_customizer'] is False


def test_owner_report_is_private_filterable_and_exportable(env):
    app, admin, employee = env
    assert employee.get('/api/admin/reports').status_code == 403
    response = admin.get('/api/admin/reports')
    assert response.status_code == 200
    report = response.json()
    assert set(report) == {'period', 'totals', 'services', 'orders'}
    assert {'revenue_cents', 'collected_cents', 'cost_cents', 'profit_cents', 'margin_percent'} <= set(report['totals'])
    assert report['totals']['order_count'] == len(report['orders'])
    assert admin.get('/api/admin/reports?start=not-a-date').status_code == 422

    exported = admin.get('/api/admin/reports.csv')
    assert exported.status_code == 200
    assert exported.headers['content-type'].startswith('text/csv')
    assert 'attachment; filename="tampa-signs-owner-report.csv"' == exported.headers['content-disposition']
    assert exported.text.startswith('Order,Date,Customer,Project,Booked,Revenue')


def test_frontend_exposes_reports_and_product_icons_without_contour_designer():
    app_js = open('app/static/app.js', encoding='utf-8').read()
    shop_js = open('app/static/shop.js', encoding='utf-8').read()
    assert "['reports','chart','Revenue & reports']" in app_js
    assert "'/api/admin/reports'" in app_js
    assert 'product-catalog-card' in shop_js
    assert 'Create live contour-cut proof' not in shop_js
    assert 'customer-contour-proof.png' not in shop_js
