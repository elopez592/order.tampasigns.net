from tests.conftest import create_banner, portal, image_bytes


def _line(line, source_index):
    return {
        'source_index': source_index,
        'name': line['name'],
        'description': line.get('description', ''),
        'quantity': line['quantity'],
        'unit': line.get('unit', 'each'),
        'width': line.get('width', ''),
        'height': line.get('height', ''),
        'sell_total': line['sell_cents'] / 100,
        'cost_total': line['cost_cents'] / 100,
        'artwork_required': True,
    }


def test_owner_can_add_edit_reorder_and_remove_quote_service_lines(env):
    app, admin, employee = env
    job_id = create_banner(admin)
    before = admin.get(f'/api/staff/jobs/{job_id}').json()
    original = before['quote']['lines'][0]
    original_subtotal = before['quote']['subtotal_cents']

    payload = {
        'version': before['quote_version'],
        'charges_verified': True,
        'deposit_percent': '50',
        'shipping': '0',
        'tax': '0',
        'lines': [
            {
                'source_index': None,
                'name': 'Installation',
                'description': 'On-site banner installation',
                'quantity': 2,
                'unit': 'hours',
                'width': '',
                'height': '',
                'sell_total': '150.00',
                'cost_total': '70.00',
                'artwork_required': False,
            },
            _line(original, 0),
        ],
    }
    response = admin.post(f'/api/staff/jobs/{job_id}/quote', json=payload)
    assert response.status_code == 200, response.text

    revised = admin.get(f'/api/staff/jobs/{job_id}').json()
    assert [x['name'] for x in revised['quote']['lines']] == ['Installation', original['name']]
    service = revised['quote']['lines'][0]
    assert service['manual_quote_line'] is True
    assert service['sell_cents'] == 15000
    assert service['cost_cents'] == 7000
    assert service['artwork_required'] is False
    assert service['width'] == ''
    assert revised['quote']['subtotal_cents'] == original_subtotal + 15000
    assert revised['totals']['merchandise_cents'] == original_subtotal + 15000

    client = portal(app, admin, job_id)
    public_job = client.get('/api/portal/job').json()
    assert public_job['quote']['lines'][0]['name'] == 'Installation'
    assert public_job['quote']['lines'][0]['sell_cents'] == 15000
    assert 'cost_cents' not in public_job['quote']['lines'][0]

    response = admin.post(f'/api/staff/jobs/{job_id}/quote', json={
        'version': revised['quote_version'],
        'charges_verified': True,
        'lines': [{
            **_line(revised['quote']['lines'][1], 1),
            'description': 'Updated banner scope',
            'sell_total': '225.00',
        }],
    })
    assert response.status_code == 200, response.text
    final = admin.get(f'/api/staff/jobs/{job_id}').json()
    assert len(final['quote']['lines']) == 1
    assert final['quote']['lines'][0]['description'] == 'Updated banner scope'
    assert final['quote']['lines'][0]['sell_cents'] == 22500


def test_service_line_is_not_required_for_generated_artwork_layout(env):
    app, admin, employee = env
    job_id = create_banner(admin)
    before = admin.get(f'/api/staff/jobs/{job_id}').json()
    original = before['quote']['lines'][0]

    response = admin.post(f'/api/staff/jobs/{job_id}/quote', json={
        'version': before['quote_version'],
        'charges_verified': True,
        'lines': [
            _line(original, 0),
            {
                'source_index': None,
                'name': 'Design service',
                'description': 'Layout cleanup',
                'quantity': 1,
                'unit': 'service',
                'width': '',
                'height': '',
                'sell_total': '75',
                'cost_total': '25',
                'artwork_required': False,
            },
        ],
    })
    assert response.status_code == 200, response.text

    upload = admin.post(f'/api/jobs/{job_id}/artwork',
                        files={'file': ('art.png', image_bytes(), 'image/png')})
    assert upload.status_code == 200, upload.text
    asset_id = upload.json()['asset_id']

    layout = employee.post(f'/api/staff/jobs/{job_id}/layout', json={
        'artwork': {'0': asset_id},
        'fit': 'contain',
        'publish_as_proof': True,
    })
    assert layout.status_code == 200, layout.text
