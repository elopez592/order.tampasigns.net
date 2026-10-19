from .conftest import anonymous


def test_die_cut_prices_scale_with_size_and_quantity(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()['products']
    stickers = next(p for p in catalog if p['name'] == 'Die-cut stickers')
    labels = next(p for p in catalog if p['name'] == 'Labels')

    def quote(product, width, height, qty):
        response = client.post('/api/calculate', json={'items': [{
            'product_id': product['id'], 'width': width, 'height': height,
            'quantity': qty, 'lamination': 'none'
        }]})
        assert response.status_code == 200, response.text
        return response.json()['subtotal_cents']

    # This is the owner-approved small die-cut benchmark, before tax/delivery.
    assert quote(stickers, '1.7', '1.4', 700) == 24502
    assert quote(labels, '1.7', '1.4', 700) < quote(stickers, '1.7', '1.4', 700)
    for width, height in [(1, 1), (1.7, 1.4), (2, 2), (3, 3), (4, 4)]:
        prices = [quote(stickers, width, height, qty) for qty in [50, 100, 500, 700, 1000]]
        assert prices == sorted(prices)
        assert all(quote(stickers, width, height, qty) > quote(labels, width, height, qty)
                   for qty in [50, 100, 500, 700, 1000])
    for qty in [50, 700, 1000]:
        assert quote(stickers, 1, 1, qty) < quote(stickers, 1.7, 1.4, qty)
        assert quote(stickers, 1.7, 1.4, qty) < quote(stickers, 3, 3, qty)


def test_wrap_multi_panel_install_estimate_and_lamination(env):
    app, admin, employee = env
    client = anonymous(app)
    wrap = next(p for p in client.get('/api/catalog').json()['products'] if p['name'] == 'Vehicle Wraps')
    items = [
        {'product_id':wrap['id'],'width':54,'height':120,'quantity':1,'installation_requested':True,'lamination':'cast_gloss'},
        {'product_id':wrap['id'],'width':54,'height':60,'quantity':1,'installation_requested':True,'lamination':'cast_gloss'},
    ]
    r=client.post('/api/calculate',json={'items':items})
    assert r.status_code==200,r.text
    data=r.json()
    assert len(data['lines'])==2
    assert data['review_required'] is True
    assert data['subtotal_cents'] > 0
    assert sum(x['installation_estimate_cents'] for x in data['lines']) > 0


def test_custom_request_accepts_optional_multiple_dimensions(env):
    app, admin, employee = env
    client = anonymous(app)
    r=client.post('/api/custom-requests',json={
        'customer_name':'Test Customer','customer_email':'custom@example.test',
        'project_type':'Fleet / multiple vehicles','notes':'Need a custom fleet quote.',
        'dimensions':[
            {'label':'Driver side','width':'120','height':'48','quantity':3},
            {'label':'Passenger side','width':'120','height':'48','quantity':3},
        ]
    })
    assert r.status_code==200,r.text
    job=admin.get('/api/staff/jobs/'+str(r.json()['job_id'])).json()
    assert len(job['quote']['lines'])==2
    assert 'Driver side' in job['notes']
