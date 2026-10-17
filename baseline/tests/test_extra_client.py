"""Exercise extra-client behavior without running Wine or accessing the live DB."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import extra_client


class ExtraClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.client=self.root/'reference-runtime/client/Gunz.exe'
        self.client.parent.mkdir(parents=True);self.client.write_bytes(b'fixture')
        self.log=self.root/'reference-runtime/server-console.log'
        self.log.write_text('Match Server Created (Port:6000)\n')
        env=patch.dict(os.environ,{'WINEPREFIX':'/work/reference-home/game-wine'});env.start();self.addCleanup(env.stop)

    def test_only_launches_existing_runtime_client(self):
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(extra_client.socket,'create_connection') as connect,patch.object(extra_client.subprocess,'call',return_value=0) as call:
            self.assertEqual(extra_client.main(self.root),0)
            connect.assert_called_once_with(('127.0.0.1',6000),timeout=2)
            call.assert_called_once_with(['wine',str(self.client),'launch'],cwd=self.client.parent)
        after={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_failed_server_does_not_open_client(self):
        self.log.write_text('Read Item Descriptor Failed\nMMatchServer::Create failed\n')
        with patch.object(extra_client.subprocess,'call') as call:
            with self.assertRaisesRegex(RuntimeError,'not ready'):extra_client.main(self.root)
            call.assert_not_called()

    def test_dead_listener_does_not_open_client(self):
        with patch.object(extra_client.socket,'create_connection',side_effect=ConnectionRefusedError),patch.object(extra_client.subprocess,'call') as call:
            with self.assertRaisesRegex(RuntimeError,'not accepting connections'):extra_client.main(self.root)
            call.assert_not_called()

    def test_missing_client_does_not_launch(self):
        self.client.unlink()
        with patch.object(extra_client.subprocess,'call') as call:
            with self.assertRaisesRegex(RuntimeError,'no prepared client'):extra_client.main(self.root)
            call.assert_not_called()

    def test_wrong_prefix_rejected(self):
        with patch.dict(os.environ,{'WINEPREFIX':'/work/reference-home/compiler-wine'}),patch.object(extra_client.subprocess,'call') as call:
            with self.assertRaisesRegex(RuntimeError,'session Wine prefix'):extra_client.main(self.root)
            call.assert_not_called()

    def test_child_failure_does_not_stop_session(self):
        with patch.object(extra_client.socket,'create_connection'),patch.object(extra_client.subprocess,'call',return_value=7) as call:
            self.assertEqual(extra_client.main(self.root),7)
            self.assertEqual(call.call_count,1) # No cleanup, restart or wineserver -k.


if __name__=='__main__':unittest.main()