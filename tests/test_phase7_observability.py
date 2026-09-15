from app.observability import init_observability


def _observed(app, monkeypatch):
    monkeypatch.setenv('HMS_LOG_FORMAT', 'text')
    monkeypatch.setenv('HMS_HEALTH_REQUIRE_REDIS', '0')
    monkeypatch.setenv('HMS_METRICS_ENABLED', '1')
    init_observability(app)
    return app.test_client()


def test_liveness_probe_does_not_require_dependencies(app, monkeypatch):
    client = _observed(app, monkeypatch)
    response = client.get('/health/live')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'


def test_readiness_probe_checks_database(app, monkeypatch):
    client = _observed(app, monkeypatch)
    response = client.get('/health/ready')
    body = response.get_json()
    assert response.status_code == 200
    assert body['status'] == 'ready'
    assert body['dependencies']['database']['ok'] is True
    assert body['dependencies']['redis']['required'] is False


def test_request_id_is_preserved_and_returned(app, monkeypatch):
    client = _observed(app, monkeypatch)
    response = client.get('/health/live', headers={'X-Request-ID': 'test-request-123'})
    assert response.headers['X-Request-ID'] == 'test-request-123'


def test_invalid_request_id_is_replaced(app, monkeypatch):
    client = _observed(app, monkeypatch)
    response = client.get('/health/live', headers={'X-Request-ID': 'bad id with spaces'})
    assert response.headers['X-Request-ID'] != 'bad id with spaces'
    assert response.headers['X-Request-ID']


def test_metrics_endpoint_exports_http_and_dependency_metrics(app, monkeypatch):
    client = _observed(app, monkeypatch)
    client.get('/health/live')
    response = client.get('/metrics')
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'hms_process_uptime_seconds' in text
    assert 'hms_http_requests_total' in text
    assert 'hms_dependency_up{dependency="database"} 1' in text
