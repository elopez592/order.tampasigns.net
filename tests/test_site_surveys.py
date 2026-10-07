import io

from PIL import Image

from .conftest import anonymous, image_bytes, portal
from .test_company_platform import add_company, tenant
from .test_employee_mobile import add_client, estimate, save_survey


def upload_photo(client, survey_id, key='photo', panel_key=''):
    response = client.post(f'/api/staff/surveys/{survey_id}/files',
                           files={'file': ('site.png', image_bytes(), 'image/png')},
                           data={'client_key': key, 'panel_key': panel_key})
    assert response.status_code == 200, response.text
    return response.json()['id']


def test_browse_saved_surveys_including_standalone_and_job_metadata(env):
    app, admin, employee = env
    cid = add_client(employee)
    standalone, _ = save_survey(employee, cid)
    jid, _, _ = estimate(employee, cid)
    linked, _ = save_survey(employee, cid, job_id=jid)
    photo_id = upload_photo(employee, linked['id'], panel_key='area-0')
    data = admin.get('/api/staff/surveys?summary=true&limit=12').json()
    assert data['total'] == 2
    assert data['totals'] == {'surveys': 2, 'submitted': 0, 'draft': 2, 'verified': 0, 'photos': 1}
    rows = {s['id']: s for s in data['surveys']}
    assert rows[standalone['id']]['job_id'] is None
    assert rows[linked['id']]['job_number'] == admin.get(f'/api/staff/jobs/{jid}').json()['number']
    assert rows[linked['id']]['employee_name'] == employee.get('/api/session').json()['user']['name']
    assert rows[linked['id']]['area_count'] == rows[linked['id']]['photo_count'] == 1
    assert 'measurements' not in rows[linked['id']]
    full = admin.get(f'/api/staff/surveys/{linked["id"]}').json()
    assert full['client_name'] == 'Survey Shop' and full['contact_name'] == 'Survey Client'
    assert full['measurements'][0]['product_name']
    assert full['files'][0]['id'] == photo_id
    assert 'payload_hash' not in full and 'stored_name' not in full['files'][0]
    # Existing mobile callers still receive full measured areas without summary mode.
    assert employee.get('/api/staff/surveys').json()['surveys'][0]['measurements']


def test_search_status_contact_job_filters_and_pagination(env):
    _, admin, employee = env
    cid = add_client(employee)
    first, _ = save_survey(employee, cid)
    second, _ = save_survey(employee, cid)
    jid, _, _ = estimate(employee, cid)
    third, _ = save_survey(employee, cid, job_id=jid)
    assert employee.post(f'/api/staff/surveys/{second["id"]}/action',
                         json={'action': 'submit', 'version': second['version']}).status_code == 200
    assert admin.get('/api/staff/surveys?summary=true&status=submitted').json()['surveys'][0]['id'] == second['id']
    assert admin.get('/api/staff/surveys?summary=true&status=draft').json()['total'] == 2
    for search in ('survey shop', '123 test street', 'field-one@example.test',
                   employee.get('/api/session').json()['user']['name']):
        assert admin.get('/api/staff/surveys', params={'q': search, 'summary': True}).json()['total'] == 3
    number = admin.get(f'/api/staff/jobs/{jid}').json()['number']
    assert admin.get('/api/staff/surveys', params={'q': number}).json()['surveys'][0]['id'] == third['id']
    assert admin.get('/api/staff/surveys', params={'job_id': jid}).json()['total'] == 1
    assert admin.get('/api/staff/surveys', params={'contact_id': cid}).json()['total'] == 3
    all_ids = [r['id'] for r in admin.get('/api/staff/surveys').json()['surveys']]
    pages = [admin.get('/api/staff/surveys', params={'limit': 1, 'offset': i, 'summary': True}).json()['surveys'][0]['id'] for i in range(3)]
    assert pages == all_ids and set(pages) == {first['id'], second['id'], third['id']}
    assert admin.get('/api/staff/surveys?q=%25').json()['total'] == 0
    assert admin.get('/api/staff/surveys?status=invalid').status_code == 422
    assert admin.get('/api/staff/surveys?limit=0').status_code == 422
    assert admin.get('/api/staff/surveys?offset=-1').status_code == 422


def test_photos_have_small_private_thumbnails_and_full_downloads(env):
    app, admin, employee = env
    cid = add_client(employee)
    survey, _ = save_survey(employee, cid)
    file_id = upload_photo(employee, survey['id'])
    file = admin.get(f'/api/staff/surveys/{survey["id"]}').json()['files'][0]
    original = employee.get(file['url'])
    preview = admin.get(file['thumbnail_url'])
    assert original.status_code == preview.status_code == 200
    assert original.headers['cache-control'] == preview.headers['cache-control'] == 'no-store'
    assert Image.open(io.BytesIO(original.content)).size == (600, 300)
    assert Image.open(io.BytesIO(preview.content)).size == (480, 240)
    assert preview.headers['content-type'] == 'image/jpeg'
    downloaded = admin.get(file['download_url'])
    assert downloaded.content == original.content
    assert downloaded.headers['content-disposition'].startswith('attachment;')
    assert original.headers['content-disposition'].startswith('inline;')
    other, _ = save_survey(employee, cid)
    assert admin.get(f'/api/staff/surveys/{other["id"]}/files/{file_id}/thumbnail').status_code == 404
    visitor = anonymous(app)
    for url in ('/api/staff/surveys?summary=true', file['thumbnail_url'], file['url'], file['download_url']):
        assert visitor.get(url).status_code == 401
    jid, _, _ = estimate(employee, cid)
    customer = portal(app, admin, jid)
    assert customer.get(file['thumbnail_url']).status_code == 401


def test_pdf_is_a_downloadable_file_without_a_photo_thumbnail(env):
    _, admin, employee = env
    cid = add_client(employee)
    survey, _ = save_survey(employee, cid)
    saved = employee.post(f'/api/staff/surveys/{survey["id"]}/files',
                          files={'file': ('site-plan.pdf', b'%PDF-1.4\n%%EOF', 'application/pdf')},
                          data={'client_key': 'plan'})
    assert saved.status_code == 200
    file = admin.get(f'/api/staff/surveys/{survey["id"]}').json()['files'][0]
    assert file['thumbnail_url'] is None
    assert admin.get(file['download_url']).headers['content-type'] == 'application/pdf'
    assert admin.get(file['url']+'/thumbnail').status_code == 404
    assert admin.get('/api/staff/surveys?summary=true').json()['totals']['photos'] == 0


def test_survey_browser_and_photos_are_isolated_between_companies(env):
    app, admin, employee = env
    root_cid = add_client(employee)
    root_survey, _ = save_survey(employee, root_cid)
    root_file = upload_photo(employee, root_survey['id'])
    child = tenant(app, 'survey-gallery.example.test', add_company(admin, 'survey-gallery', 'survey-gallery.example.test'))
    try:
        assert child.get('/api/staff/surveys?summary=true').json()['total'] == 0
        assert child.get(f'/api/staff/surveys/{root_survey["id"]}').status_code == 404
        assert child.get(f'/api/staff/surveys/{root_survey["id"]}/files/{root_file}/thumbnail').status_code == 404
        cid = add_client(child, suffix='child')
        saved, _ = save_survey(child, cid)
        upload_photo(child, saved['id'])
        assert child.get('/api/staff/surveys?summary=true').json()['total'] == 1
        assert admin.get('/api/staff/surveys?summary=true').json()['total'] == 1
        assert child.get(f'/api/staff/surveys/{saved["id"]}').json()['employee_name'] != root_survey['employee_name']
    finally:
        child.close()
