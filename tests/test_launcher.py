import os
import socket

import pytest

from scripts.dev import check_port


def test_live_listener_is_rejected():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with pytest.raises(RuntimeError, match="already in use"):
            check_port(server.getsockname()[1])


@pytest.mark.skipif(os.name == "nt", reason="POSIX TIME_WAIT reuse semantics")
def test_recently_closed_connection_does_not_prevent_stack_restart():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        with socket.create_connection(("127.0.0.1", port)) as client:
            accepted, _ = server.accept()
            accepted.close()  # Server actively closes: this endpoint enters TIME_WAIT.
            assert client.recv(1) == b""
    check_port(port)
