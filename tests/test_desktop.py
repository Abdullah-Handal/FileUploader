import pytest

import desktop


def test_a_port_in_use_cannot_be_bound_twice():
    # Windows lets SO_REUSEADDR share a listening port, which made a second copy
    # of the app bind 8765 beside the first. CI runs this on Windows.
    first, port = desktop._reserve_port(0)
    try:
        with pytest.raises(OSError):
            desktop._reserve_port(port)
    finally:
        first.close()


def test_server_only_listens_on_loopback():
    sock, _ = desktop._reserve_port(0)
    try:
        assert sock.getsockname()[0] == "127.0.0.1"
    finally:
        sock.close()
