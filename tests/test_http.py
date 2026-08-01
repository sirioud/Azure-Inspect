"""Tests for the shared _http Azure REST helper."""
from unittest import mock

import pytest

from azure_inspect import _http
from azure_inspect.config import AzureConfig


@pytest.fixture
def cfg():
    return AzureConfig("t", "c", "s", "sub-123")


def _fake_resp(status, json_data=None, text="", next_link=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = json_data or {}
    resp.text = text
    if next_link is not None:
        resp.json.return_value = {**(json_data or {}), "nextLink": next_link}
    return resp


def test_azure_get_paginates(cfg):
    page1 = {"value": [{"name": "rg-1"}]}
    page2 = {"value": [{"name": "rg-2"}]}
    with mock.patch("azure_inspect._http.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect._http.requests.Session") as sess_cls:
        sess = sess_cls.return_value
        sess.get.side_effect = [_fake_resp(200, page1, next_link="http://next"),
                                _fake_resp(200, page2)]
        items = _http.azure_get(cfg, "http://base", paginate=True)
    assert len(items) == 2
    assert items[0]["name"] == "rg-1" and items[1]["name"] == "rg-2"
    assert sess.get.call_count == 2


def test_azure_get_retries_on_503_then_succeeds(cfg):
    with mock.patch("azure_inspect._http.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect._http.requests.Session") as sess_cls, \
         mock.patch("azure_inspect._http.time.sleep") as sleep:
        sess = sess_cls.return_value
        sess.get.side_effect = [_fake_resp(503, text="tmp"), _fake_resp(200, {"value": [{"a": 1}]})]
        items = _http.azure_get(cfg, "http://base")
    assert len(items) == 1
    assert sleep.call_count == 1  # backoff called once before retry


def test_azure_get_gives_up_after_retries(cfg):
    with mock.patch("azure_inspect._http.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect._http.requests.Session") as sess_cls, \
         mock.patch("azure_inspect._http.time.sleep"):
        sess = sess_cls.return_value
        sess.get.return_value = _fake_resp(500, text="boom")
        with pytest.raises(RuntimeError):
            _http.azure_get(cfg, "http://base")
    assert sess.get.call_count == _http._MAX_RETRIES + 1


def test_azure_post_json_success(cfg):
    with mock.patch("azure_inspect._http.get_access_token", return_value="tok"), \
         mock.patch("azure_inspect._http.requests.Session") as sess_cls:
        sess = sess_cls.return_value
        sess.post.return_value = _fake_resp(200, {"properties": {"rows": []}})
        out = _http.azure_post_json(cfg, "http://base", {"k": "v"})
    assert out == {"properties": {"rows": []}}
    sess.post.assert_called_once()
