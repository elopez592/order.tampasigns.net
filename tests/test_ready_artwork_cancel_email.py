from .conftest import anonymous, create_banner, finalize, portal, accept, image_bytes


def test_shop_minimum_is_acceptance_gate_not_price_floor(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()['products']
    banner = next(p for p in catalog if p['name'] == 'Banners')
    quote = client.post('/api/calculate', json={'items': [{
        'product_id': banner['id'], 'width': 12, 'height': 12, 'quantity': 1
    }]})
    assert quote.status_code == 200, quote.text
    data = quote.json()
    assert data['subtotal_cents'] < 5000
    assert data['minimum_order_cents'] == 5000
    assert data['meets_minimum_order'] is False
    assert data['minimum_order_adjustment_cents'] == 0


def test_sticker_minimums_are_50_pieces_and_one_inch(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()
    sticker = next(p for p in catalog['products'] if p['name'] == 'Die-cut stickers')
    assert sticker['config']['min_quantity'] == '50'
    assert sticker['config']['min_width'] == '1'
    assert sticker['config']['min_height'] == '1'
    assert sticker['config']['self_approve_artwork'] is True

    too_small = client.post('/api/calculate', json={'items': [{
        'product_id': sticker['id'], 'width': .9, 'height': 1, 'quantity': 50,
        'lamination': 'standard_matte'
    }]})
    assert too_small.status_code == 422

    valid = client.post('/api/calculate', json={'items': [{
        'product_id': sticker['id'], 'width': 1, 'height': 1, 'quantity': 50,
        'lamination': 'standard_matte'
    }]})
    assert valid.status_code == 200, valid.text
    assert valid.json()['minimum_order_cents'] == 5000
    assert valid.json()['meets_minimum_order'] is True


def test_transfer_stickers_and_low_quantity_products(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()['products']
    transfer = next(p for p in catalog if p['name'] == 'Transfer stickers')
    magnet = next(p for p in catalog if p['name'] == 'Magnets')
    banner = next(p for p in catalog if p['name'] == 'Banners')
    assert transfer['config']['min_quantity'] == '50'
    assert transfer['config']['min_width'] == '1'
    assert transfer['config']['min_height'] == '1'
    assert transfer['config']['self_approve_artwork'] is True
    assert magnet['config']['min_quantity'] == '1'
    assert magnet['config']['self_approve_artwork'] is True
    assert banner['config']['self_approve_artwork'] is True

def test_customer_can_approve_print_ready_banner_upload(env):
    app, admin, employee = env
    job_id = create_banner(admin)
    finalize(admin, job_id)
    client = portal(app, admin, job_id)
    accept(client)

    upload = client.post(
        f'/api/jobs/{job_id}/artwork',
        files={'file': ('ready.png', image_bytes(), 'image/png')}
    )
    assert upload.status_code == 200, upload.text
    asset_id = upload.json()['asset_id']

    approval = client.post(f'/api/portal/artwork/{asset_id}/approve', json={
        'name': 'Test Customer', 'confirm': True
    })
    assert approval.status_code == 200, approval.text

    job = client.get('/api/portal/job').json()
    assert job['proofs'][0]['status'] == 'approved'
    assert job['proofs'][0]['asset_id'] == asset_id
    assert job['proofs'][0]['decisions'][-1]['action'] == 'approve'


def test_staff_can_cancel_job_and_remove_it_from_queue(env):
    app, admin, employee = env
    job_id = create_banner(admin)
    response = admin.post(f'/api/staff/jobs/{job_id}/cancel', json={'reason': 'Customer cancelled'})
    assert response.status_code == 200, response.text
    jobs = admin.get('/api/staff/jobs').json()['jobs']
    assert all(j['id'] != job_id for j in jobs)
    detail = admin.get(f'/api/staff/jobs/{job_id}').json()
    assert detail['archived'] == 1


def test_staff_can_resend_pending_proof_even_when_email_not_configured(env):
    app, admin, employee = env
    job_id = create_banner(admin)
    finalize(admin, job_id)
    proof_id = admin.post(
        f'/api/staff/jobs/{job_id}/proofs',
        files={'file': ('proof.png', image_bytes(), 'image/png')},
        data={'label': 'Approval proof', 'covers_all_items': 'true'}
    ).json()['proof_id']
    response = employee.post(f'/api/staff/jobs/{job_id}/proofs/{proof_id}/send', json={})
    assert response.status_code == 200, response.text
    assert response.json()['email_sent'] is False


def test_email_status_endpoint_reports_configuration_state(env):
    app, admin, employee = env
    response = admin.get('/api/admin/email-status')
    assert response.status_code == 200
    body = response.json()
    assert body['configured'] is False
    assert body['provider'] is None
    assert isinstance(body['counts'], dict)
