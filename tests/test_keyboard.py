import sys
import threading
import types

from os_download.downloader import ui


class FakeStdin:
    def isatty(self):
        return True


def test_q_quits_on_windows(monkeypatch):
    """The footer advertises 'q' unconditionally, so it must work off POSIX too."""
    keys = iter(["x", "q"])

    fake_msvcrt = types.SimpleNamespace(kbhit=lambda: True, getwch=lambda: next(keys))
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ui.sys, "stdin", FakeStdin())
    monkeypatch.setattr(ui.time, "sleep", lambda seconds: None)

    quit_event = threading.Event()
    ui.keyboard_listener(quit_event, threading.Event())

    assert quit_event.is_set()


def test_listener_exits_immediately_when_stdin_is_not_a_terminal(monkeypatch):
    class NotATty:
        def isatty(self):
            return False

    monkeypatch.setattr(ui.sys, "stdin", NotATty())

    quit_event = threading.Event()
    ui.keyboard_listener(quit_event, threading.Event())

    assert not quit_event.is_set()
