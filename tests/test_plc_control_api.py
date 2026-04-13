"""Unit tests for mock PLC HTTP control API."""
import pytest
from unittest.mock import MagicMock

try:
    from mock.cip_plc import CIPPLC, FLASK_AVAILABLE
    from mock.tag_manager import OperatingMode
    CIPPPC_IMPORTABLE = True
except ImportError:
    CIPPPC_IMPORTABLE = False
    FLASK_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not CIPPPC_IMPORTABLE or not FLASK_AVAILABLE,
    reason="cip_plc or Flask not importable"
)


@pytest.fixture
def plc_instance():
    """Create a CIPPLC instance with cpppo dependency mocked out."""
    # Patch CPPPO_AVAILABLE so __init__ doesn't raise
    import mock.cip_plc as cip_mod
    original = cip_mod.CPPPO_AVAILABLE
    cip_mod.CPPPO_AVAILABLE = True

    # Stub the heavy components so we don't need a real cpppo install
    from unittest.mock import patch, MagicMock
    with patch('mock.cip_plc.TagManager') as mock_tm, \
         patch('mock.cip_plc.TagObject'), \
         patch('mock.cip_plc.ConnectionManager'), \
         patch('mock.cip_plc.IdentityObject'), \
         patch('mock.cip_plc.CIPServiceHandler'):
        mock_tm.return_value = MagicMock()
        plc = CIPPLC(ip='127.0.0.1', port=44818, control_port=18080)

    cip_mod.CPPPO_AVAILABLE = original
    return plc


@pytest.fixture
def control_client(plc_instance):
    """Flask test client for the control API."""
    app = plc_instance.build_control_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health_returns_ok(control_client, plc_instance):
    plc_instance.mode = OperatingMode.NORMAL
    resp = control_client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['mode'] == 'normal'


def test_get_mode_returns_current_mode(control_client, plc_instance):
    plc_instance.mode = OperatingMode.NORMAL
    resp = control_client.get('/mode')
    assert resp.status_code == 200
    assert resp.get_json()['mode'] == 'normal'


def test_put_mode_changes_mode(control_client, plc_instance):
    resp = control_client.put('/mode', json={'mode': 'failed'})
    assert resp.status_code == 200
    assert resp.get_json()['mode'] == 'failed'
    assert plc_instance.mode == OperatingMode.FAILED


def test_put_mode_invalid_returns_400(control_client):
    resp = control_client.put('/mode', json={'mode': 'exploded'})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_reset_sets_normal_mode(control_client, plc_instance):
    plc_instance.mode = OperatingMode.FAILED
    resp = control_client.post('/reset')
    assert resp.status_code == 200
    assert resp.get_json()['mode'] == 'normal'
    assert plc_instance.mode == OperatingMode.NORMAL
