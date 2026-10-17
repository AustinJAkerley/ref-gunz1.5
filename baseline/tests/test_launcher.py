"""Launcher checks with fake Docker responses. Never starts Wine or the game."""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gunz_launcher", ROOT / "launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def host_main(self, args, state=""):
        # Force only the Flatpak detector off, independent of where tests run.
        exists = Path.exists
        with patch.object(Path, "exists", lambda p: False if str(p) == "/.flatpak-info" else exists(p)), \
             patch.object(launcher.sys, "platform", "linux"), \
             patch.object(launcher, "docker_path", return_value="/usr/bin/docker"), \
             patch.object(launcher, "check_setup", return_value=state), \
             patch.object(launcher, "display_mounts", return_value=["--env", "DISPLAY=:1"]), \
             patch.object(launcher.subprocess, "call", return_value=0) as call, \
             redirect_stdout(io.StringIO()) as output:
            result = launcher.main(args)
            return result, call.call_args_list, output.getvalue()

    def test_login_is_default_and_no_flatpak_dependency(self):
        code, calls, _ = self.host_main([])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        command = calls[0].args[0]
        self.assertEqual(command[0], "/usr/bin/docker")
        self.assertEqual(command[-1], "--login")
        self.assertNotIn("flatpak-spawn", command)
        self.assertIn("--pull=never", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertNotIn("--privileged", command)
        self.assertNotIn("-p", command)

    def test_practice_is_explicit(self):
        code, calls, _ = self.host_main(["--practice"])
        self.assertEqual(code, 0)
        self.assertNotIn("--login", calls[0].args[0])
        self.assertEqual(calls[0].args[0][-1], "/baseline/runtime.py")

    def test_check_does_not_launch(self):
        code, calls, output = self.host_main(["--check"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertIn("Check only", output)

    def test_existing_session_not_restarted_or_focused(self):
        code, calls, output = self.host_main([], state="running")
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertIn("already running", output)
        self.assertIn("--extra-client", output)

    def test_extra_client_uses_existing_container_only(self):
        with patch.object(launcher.os,"getuid",return_value=1234), patch.object(launcher.os,"getgid",return_value=5678):
            code,calls,output=self.host_main(["--extra-client"],state="running")
        self.assertEqual(code,0)
        self.assertEqual(len(calls),1)
        command=calls[0].args[0]
        self.assertEqual(command[:2],["/usr/bin/docker","exec"])
        self.assertEqual(command[command.index("--user")+1],"1234:5678")
        self.assertEqual(command[-3:],[launcher.SESSION,"python3","/baseline/extra_client.py"])
        self.assertIn("WINEPREFIX=/work/reference-home/game-wine",command)
        for forbidden in ("run","restart","stop","kill","--network","/baseline/runtime.py"):
            self.assertNotIn(forbidden,command)
        self.assertIn("DIFFERENT account",output)
        self.assertIn("Keep the original client open",output)

    def test_extra_client_needs_running_session(self):
        for state in ("","exited","paused"):
            with self.subTest(state=state),self.assertRaisesRegex(launcher.LauncherError,"Start GunZ normally first"):
                self.host_main(["--extra-client"],state=state)

    def test_extra_client_check_never_executes(self):
        code,calls,output=self.host_main(["--extra-client","--check"],state="running")
        self.assertEqual(code,0)
        self.assertEqual(calls,[])
        self.assertIn("extra login client",output)

    def test_extra_client_inherits_existing_display(self):
        # Existing container display is used even when the invoking shell has none.
        with patch.dict(launcher.os.environ,{"DISPLAY":"","XAUTHORITY":"/missing"}):
            code,calls,_=self.host_main(["--extra-client"],state="running")
        self.assertEqual(code,0)
        self.assertFalse(any("DISPLAY=" in arg or "XAUTHORITY=" in arg for arg in calls[0].args[0]))

    def test_extra_client_rejects_incompatible_modes(self):
        for flag in ("--practice","--login","--install-shortcut","--seconds"):
            args=["--extra-client",flag]+(["5"] if flag=="--seconds" else [])
            with self.subTest(flag=flag),self.assertRaises(SystemExit):self.host_main(args,state="running")

    def test_stopped_container_not_deleted(self):
        with self.assertRaisesRegex(launcher.LauncherError, "not changed"):
            self.host_main([], state="exited")

    def test_missing_build_fails_before_docker(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher, "ROOT", Path(directory)), \
             patch.object(launcher, "checked_output") as execute:
            with self.assertRaisesRegex(launcher.LauncherError, "not been built"):
                launcher.check_setup("docker")
            execute.assert_not_called()

    def test_docker_errors_are_actionable(self):
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(launcher, "checked_output", side_effect=launcher.LauncherError("permission denied")):
            with self.assertRaisesRegex(launcher.LauncherError, "permission"):
                launcher.check_setup("docker")

    def test_missing_image_does_not_pull(self):
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(launcher, "checked_output", side_effect=["29", launcher.LauncherError("missing")]) as execute:
            with self.assertRaisesRegex(launcher.LauncherError, "Wine image is missing"):
                launcher.check_setup("docker")
            self.assertEqual(execute.call_count, 2)

    def test_local_display_and_authority_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            authority = Path(directory) / "desktop auth"
            authority.write_bytes(b"test-cookie")
            with patch.object(Path, "exists", return_value=True):
                args = launcher.display_mounts({"DISPLAY": ":3.0", "XAUTHORITY": str(authority)})
            self.assertIn("DISPLAY=:3.0", args)
            self.assertIn(f"type=bind,source={authority},target=/run/gunz.xauth,readonly", args)
            self.assertNotIn("test-cookie", " ".join(args))

    def test_remote_or_missing_display_rejected(self):
        for display in ("", "host:1", "localhost:10", ":x"):
            with self.subTest(display=display), self.assertRaises(launcher.LauncherError):
                launcher.display_mounts({"DISPLAY": display})

    def test_paths_with_spaces_are_single_arguments(self):
        with patch.object(launcher, "ROOT", Path("/home/test/Game Projects/GunZ")), \
             patch.object(launcher.os, "getuid", return_value=1234), \
             patch.object(launcher.os, "getgid", return_value=5678):
            args = argparse.Namespace(practice=False, seconds=None)
            command = launcher.launch_command("docker", args, [])
            self.assertIn("1234:5678", command)
            self.assertIn("type=bind,source=/home/test/Game Projects/GunZ/build,target=/work", command)

    def test_shortcut_installs_without_launching(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch.object(Path, "home", return_value=home), \
                 patch.dict(launcher.os.environ, {"XDG_DATA_HOME": str(home / ".local/share")}), \
                 patch.object(launcher.shutil, "which", return_value="/usr/bin/xdg-user-dir"), \
                 patch.object(launcher, "checked_output", return_value=str(home / "Desktop")), \
                 patch.object(launcher.subprocess, "call") as call, redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.install_shortcuts(), 0)
                call.assert_not_called()
                desktop = home / "Desktop/GunZ.desktop"
                self.assertIn("launch.py", desktop.read_text())
                self.assertNotIn("flatpak run", desktop.read_text())
                self.assertTrue(desktop.stat().st_mode & 0o100)
                desktop.write_text("[Desktop Entry]\nName=Unrelated\n")
                with self.assertRaisesRegex(launcher.LauncherError, "unrelated"):
                    launcher.install_shortcuts()


if __name__ == "__main__":
    unittest.main()