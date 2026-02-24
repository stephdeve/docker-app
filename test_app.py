import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_hello_returns_200(client):
    response = client.get('/')
    assert response.status_code == 200

def test_hello_contains_bonjour(client):
    response = client.get('/')
    assert b'Bonjour' in response.data

def test_health_endpoint(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'

def test_metrics_endpoint(client):
    response = client.get('/metrics')
    assert response.status_code == 200
