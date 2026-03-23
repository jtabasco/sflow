import pytest
from unittest.mock import MagicMock


def test_paste_calls_attach_thread_input(mocker):
    mocker.patch("clipboard_paster.win32gui")
    mocker.patch("clipboard_paster.win32process")
    mocker.patch("clipboard_paster.win32api")
    from clipboard_paster import ClipboardPaster
    app_mock = MagicMock()
    paster = ClipboardPaster(qt_app=app_mock)
    paster.paste("hello", hwnd=12345)
    import clipboard_paster as cp
    assert cp.win32gui.AttachThreadInput.call_count == 2  # attach + detach


def test_paste_sets_clipboard_text(mocker):
    mocker.patch("clipboard_paster.win32gui")
    mocker.patch("clipboard_paster.win32process")
    mocker.patch("clipboard_paster.win32api")
    from clipboard_paster import ClipboardPaster
    app_mock = MagicMock()
    paster = ClipboardPaster(qt_app=app_mock)
    paster.paste("my text", hwnd=12345)
    app_mock.clipboard.return_value.setText.assert_called_once_with("my text")


def test_paste_sends_ctrl_v(mocker):
    mocker.patch("clipboard_paster.win32gui")
    mocker.patch("clipboard_paster.win32process")
    mock_win32api = mocker.patch("clipboard_paster.win32api")
    from clipboard_paster import ClipboardPaster
    app_mock = MagicMock()
    paster = ClipboardPaster(qt_app=app_mock)
    paster.paste("hello", hwnd=12345)
    assert mock_win32api.keybd_event.call_count >= 4
