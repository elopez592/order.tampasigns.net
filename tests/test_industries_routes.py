from tests.conftest import anonymous


def test_industries_index_and_guides_load_on_direct_navigation(env):
    app, _, _ = env
    client = anonymous(app)
    for path in ['/industries', '/industries/restaurants', '/industries/contractors', '/industries/events']:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert 'text/html' in response.headers['content-type']
        assert '/static/app.js' in response.text
