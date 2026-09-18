from .conftest import anonymous


def test_sticker_benchmark_quantity_breaks(env):
    app, admin, employee = env
    client = anonymous(app)
    sticker = next(p for p in client.get('/api/catalog').json()['products'] if p['name'] == 'Die-cut stickers')
    expected = {
        50:6000, 100:7300, 200:9500, 300:11500, 500:15200,
        1000:23200, 2000:37100, 3000:49600, 5000:72300, 10000:122500
    }
    totals = {}
    for qty in expected:
        r = client.post('/api/calculate', json={'items':[{
            'product_id':sticker['id'],'width':3,'height':3,'quantity':qty,
            'lamination':'standard_matte'
        }]})
        assert r.status_code == 200, r.text
        totals[qty] = r.json()['subtotal_cents']
    assert totals == expected


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
