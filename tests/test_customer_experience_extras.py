import json
from urllib.parse import parse_qs, urlsplit

from app.db import transaction
from .conftest import create_banner, finalize, portal


def test_limited_status_link_and_qr_do_not_expose_private_job_data(env):
    app, admin, _ = env
    job_id = create_banner(admin)
    finalize(admin, job_id)
    customer = portal(app, admin, job_id)

    response = customer.post('/api/portal/status-link')
    assert response.status_code == 200, response.text
    payload = response.json()
    token = parse_qs(urlsplit(payload['status_url']).fragment)['token'][0]

    public = customer.get('/api/status', params={'token': token})
    assert public.status_code == 200, public.text
    status = public.json()
    assert set(status) == {'number', 'stage', 'label'}
    assert status['number'].startswith('JOB-')
    assert 'customer' not in public.text.lower()
    assert 'quote' not in status

    qr = customer.get('/api/status/qr', params={'token': token})
    assert qr.status_code == 200
    assert qr.headers['content-type'] == 'image/png'
    assert qr.content.startswith(b'\x89PNG')


def test_verified_review_requires_finished_project_and_is_product_specific(env):
    app, admin, _ = env
    job_id = create_banner(admin)
    finalize(admin, job_id)
    customer = portal(app, admin, job_id)

    blocked = customer.post('/api/portal/review', json={'rating': 5, 'comment': 'Great work'})
    assert blocked.status_code == 409

    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE tasks SET status='done',completed_at='2026-09-26T00:00:00Z' WHERE job_id=?", (job_id,))
        job = conn.execute('SELECT quote_snapshot FROM jobs WHERE id=?', (job_id,)).fetchone()
        product_id = json.loads(job['quote_snapshot'])['lines'][0]['product_id']

    saved = customer.post('/api/portal/review', json={'rating': 5, 'comment': 'Great work'})
    assert saved.status_code == 200, saved.text

    reviews = customer.get(f'/api/reviews/{product_id}')
    assert reviews.status_code == 200
    body = reviews.json()
    assert body['count'] == 1
    assert body['average'] == 5.0
    assert body['reviews'][0]['verified'] is True
    assert body['reviews'][0]['comment'] == 'Great work'
