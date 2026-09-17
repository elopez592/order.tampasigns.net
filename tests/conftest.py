from __future__ import annotations
import io
from urllib.parse import urlsplit, parse_qs
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import create_app

ADMIN_PASSWORD = 'OwnerTestPassword-OnlyForTests2026'


def anonymous(app):
    client = TestClient(app).__enter__()
    if not hasattr(app.state, 'test_clients'):
        app.state.test_clients = []
    app.state.test_clients.append(client)
    client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf']
    return client


def sign_in(app, email, password):
    client = anonymous(app)
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf']
    return client


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('ADMIN_EMAIL', 'owner@example.test')
    monkeypatch.setenv('ADMIN_PASSWORD', ADMIN_PASSWORD)
    monkeypatch.setenv('PUBLIC_URL', 'http://testserver')
    monkeypatch.delenv('ALLOWED_HOSTS', raising=False)
    app = create_app(tmp_path / 'data', demo=True)
    admin = sign_in(app, 'owner@example.test', ADMIN_PASSWORD)
    employee_creds = next(c for c in app.state.initial_credentials if c[0] == 'Employee')
    employee = sign_in(app, employee_creds[1], employee_creds[2])
    try:
        yield app, admin, employee
    finally:
        for client in reversed(app.state.test_clients):
            client.__exit__(None, None, None)


def create_banner(admin):
    response = admin.post('/api/staff/jobs', json={
        'title': 'Test banner', 'customer_name': 'Test customer', 'customer_email': 'customer@example.test',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}], 'workflow_id': 2})
    assert response.status_code == 200, response.text
    return response.json()['job_id']


def finalize(admin, job_id):
    job = admin.get(f'/api/staff/jobs/{job_id}').json()
    response = admin.post(f'/api/staff/jobs/{job_id}/quote', json={
        'version': job['quote_version'], 'charges_verified': True, 'deposit_percent': '50', 'shipping': '0', 'tax': '0'})
    assert response.status_code == 200, response.text
    job = admin.get(f'/api/staff/jobs/{job_id}').json()
    response = admin.post(f'/api/staff/jobs/{job_id}/publish', json={'version': job['quote_version'], 'reviewed': True})
    assert response.status_code == 200, response.text
    return job


def portal(app, admin, job_id):
    response = admin.post(f'/api/staff/jobs/{job_id}/share')
    assert response.status_code == 200, response.text
    token = parse_qs(urlsplit(response.json()['portal_url']).fragment)['token'][0]
    client = anonymous(app)
    response = client.post('/api/portal/exchange', json={'token': token})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf']
    return client


def accept(client):
    job = client.get('/api/portal/job').json()
    response = client.post('/api/portal/accept-quote', json={'name': 'Test Customer', 'confirm': True, 'version': job['quote_version']})
    assert response.status_code == 200, response.text


def image_bytes():
    stream = io.BytesIO()
    image = Image.new('RGB', (600, 300), (35, 90, 125))
    image.save(stream, format='PNG')
    return stream.getvalue()


def proof(admin, job_id, label='Test complete package'):
    response = admin.post(f'/api/staff/jobs/{job_id}/proofs', files={'file': ('proof.png', image_bytes(), 'image/png')},
                          data={'label': label, 'covers_all_items': 'true'})
    assert response.status_code == 200, response.text
    return response.json()['proof_id']


def approve(client, proof_id):
    response = client.post(f'/api/portal/proofs/{proof_id}/decision', json={'name': 'Test Customer', 'confirm': True, 'action': 'approve'})
    assert response.status_code == 200, response.text


def task_action(client, task_id, action):
    return client.post(f'/api/staff/tasks/{task_id}/action', json={'action': action})


def finish(client, task_id):
    for action in ('start', 'complete'):
        result = task_action(client, task_id, action)
        assert result.status_code == 200, result.text


def payment(admin, job_id, amount, reference='TEST-RECEIPT-1'):
    return admin.post(f'/api/staff/jobs/{job_id}/payments', json={
        'amount': amount, 'reference': reference, 'verified_in_quickbooks': True})
