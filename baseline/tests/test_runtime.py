"""Server readiness failures must not be hidden behind the game's login screen."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import wait_for_server


class RuntimeTests(unittest.TestCase):
    def test_failed_descriptor_stops_startup(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'server.log';log.write_text('Read Item Descriptor Failed\nMMatchServer::Create failed\n')
            server=Mock();server.poll.return_value=None
            with self.assertRaisesRegex(RuntimeError,'Read Item Descriptor Failed'):wait_for_server(server,log)
            server.wait.assert_not_called()

    def test_exited_process_stops_startup(self):
        server=Mock();server.poll.return_value=1
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,'exit 1'):wait_for_server(server,Path(d)/'server.log')

    def test_ready_requires_tcp_listener(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'server.log';log.write_text('Match Server Created (Port:6000)\n')
            server=Mock();server.poll.return_value=None
            with patch('runtime.socket.create_connection') as connect:
                wait_for_server(server,log)
                connect.assert_called_once_with(('127.0.0.1',6000),timeout=.25)

    def test_missing_listener_times_out(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'server.log';log.write_text('Match Server Created (Port:6000)\n')
            server=Mock();server.poll.return_value=None
            with patch('runtime.socket.create_connection',side_effect=ConnectionRefusedError):
                with self.assertRaisesRegex(RuntimeError,'did not become ready'):wait_for_server(server,log,timeout=0)

    def test_waits_for_startup_before_checking_port(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'server.log';log.write_text('Loading descriptors\n')
            server=Mock();server.poll.return_value=None
            def becomes_ready(timeout):
                log.write_text('Match Server Created (Port:6000)\n')
                raise subprocess.TimeoutExpired('server',timeout)
            server.wait.side_effect=becomes_ready
            with patch('runtime.socket.create_connection') as connect:
                wait_for_server(server,log)
                server.wait.assert_called_once()
                connect.assert_called_once()


if __name__=='__main__':unittest.main()