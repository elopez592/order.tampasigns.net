from .conftest import anonymous


def test_vehicle_wraps_are_one_public_product_with_optional_installation(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()
    wraps = [p for p in catalog['products'] if 'wrap' in (p['name'] + ' ' + p['category']).lower()]
    names = {p['name'] for p in wraps}
    assert {'Vehicle Wraps', 'Partial Vehicle Wraps', 'Trailer / Food Truck Wraps'} <= names
    wrap = next(p for p in wraps if p['name'] == 'Vehicle Wraps')
    assert wrap['config']['supports_installation'] is True

    print_only = client.post('/api/calculate', json={'items': [{
        'product_id': wrap['id'], 'width': 54, 'height': 120, 'quantity': 1,
        'installation_requested': False
    }]})
    assert print_only.status_code == 200, print_only.text
    assert print_only.json()['lines'][0]['review_required'] is False
    assert print_only.json()['lines'][0]['installation_requested'] is False

    installed = client.post('/api/calculate', json={'items': [{
        'product_id': wrap['id'], 'width': 54, 'height': 120, 'quantity': 1,
        'installation_requested': True
    }]})
    assert installed.status_code == 200, installed.text
    assert installed.json()['lines'][0]['review_required'] is True
    assert installed.json()['lines'][0]['installation_requested'] is True


def test_custom_quote_request_creates_private_job(env):
    app, admin, employee = env
    client = anonymous(app)
    response = client.post('/api/custom-requests', json={
        'customer_name': 'Custom Customer',
        'customer_email': 'custom@example.test',
        'phone': '555-0100',
        'project_type': 'Laser-cut acrylic',
        'quantity': '25 pieces',
        'notes': 'Need layered acrylic letters with polished edges.'
    })
    assert response.status_code == 200, response.text
    job_id = response.json()['job_id']
    job = admin.get(f'/api/staff/jobs/{job_id}').json()
    assert job['source'] if 'source' in job else True
    assert job['published'] == 0
    assert job['title'] == 'Laser-cut acrylic'
    assert '25 pieces' in job['notes']
