#!/usr/bin/env python3
"""Launch the real GunZ client and local server without VS Code.

Default: login/signup. --practice: offline Mansion test mode.
--extra-client: another login client using the already-running local server.
--check and --install-shortcut never start the game or server.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
IMAGE = "gunz-baseline-toolchain:local"
SESSION = "gunz-reference-session"


class LauncherError(RuntimeError):
    pass


def checked_output(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise LauncherError(detail)
    return result.stdout.strip()


def docker_path():
    executable = shutil.which("docker")
    if not executable:
        raise LauncherError("Docker is not installed on this Linux host. See baseline/README.md for setup.")
    return executable


def display_mounts(environ):
    display = environ.get("DISPLAY", "")
    match = re.fullmatch(r":(\d+)(?:\.\d+)?", display)
    if not match:
        raise LauncherError("Run this from your local graphical desktop: a local DISPLAY/Xwayland session is required.")
    socket = Path("/tmp/.X11-unix") / ("X" + match.group(1))
    if not socket.exists():
        raise LauncherError(f"Desktop display socket is missing: {socket}")
    args = ["--env", "DISPLAY=" + display,
            "--mount", "type=bind,source=/tmp/.X11-unix,target=/tmp/.X11-unix,readonly"]
    authority = environ.get("XAUTHORITY")
    fallback = Path.home() / ".Xauthority"
    if authority or fallback.is_file():
        path = Path(authority) if authority else fallback
        path = path.resolve()
        if not path.is_file():
            raise LauncherError(f"XAUTHORITY file is missing: {path}")
        if "," in str(path):
            raise LauncherError("Docker bind-mount paths cannot contain commas.")
        args += ["--mount", f"type=bind,source={path},target=/run/gunz.xauth,readonly",
                 "--env", "XAUTHORITY=/run/gunz.xauth"]
    return args


def check_setup(docker):
    required = [
        "build/reference-win32/Gunz.exe", "build/reference-win32/MatchServer.exe",
        "build/reference-data/client/system/locale.xml", "build/reference-data/client/Maps/mansion.mrs",
        "build/reference-data/server/zitem.xml", "baseline/runtime.py", "baseline/extra_client.py",
        "baseline/config.xml", "baseline/server.ini", "baseline/system.xml",
    ]
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise LauncherError("The game has not been built/prepared. Missing: " + ", ".join(missing)
                            + ". See baseline/README.md. The launcher does not download or build anything.")
    if "," in str(ROOT):
        raise LauncherError("Docker bind-mount paths cannot contain commas.")
    try:
        checked_output([docker, "info", "--format", "{{.ServerVersion}}"])
    except LauncherError as error:
        raise LauncherError("Docker is unavailable or this user lacks permission to access it. " + str(error)) from error
    try:
        checked_output([docker, "image", "inspect", IMAGE, "--format", "{{.Id}}"])
    except LauncherError as error:
        raise LauncherError("The local GunZ Wine image is missing. See baseline/README.md for the one-time setup.") from error
    return checked_output([docker, "ps", "--all", "--filter", f"name=^/{SESSION}$", "--format", "{{.State}}"])


def launch_command(docker, args, graphics):
    command = [docker, "run", "--rm", "--pull=never", "--name", SESSION,
               "--user", f"{os.getuid()}:{os.getgid()}", "--network", "none",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--env", "HOME=/work/reference-home",
               "--env", "WINEPREFIX=/work/reference-home/game-wine", "--env", "WINEDEBUG=-all",
               "--env", "LIBGL_ALWAYS_SOFTWARE=1",
               "--mount", f"type=bind,source={ROOT}/build,target=/work",
               "--mount", f"type=bind,source={ROOT}/baseline,target=/baseline,readonly",
               *graphics, IMAGE, "python3", "/baseline/runtime.py"]
    if not args.practice:
        command.append("--login")
    if args.seconds is not None:
        command += ["--seconds", str(args.seconds)]
    return command


def extra_client_command(docker):
    # Reuse this session's network namespace, display, prefix and matching runtime
    # binary. Never start another server, copy a newer build, or touch its DB.
    return [docker, "exec", "--user", f"{os.getuid()}:{os.getgid()}",
            "--workdir", "/work/reference-runtime/client",
            "--env", "HOME=/work/reference-home",
            "--env", "WINEPREFIX=/work/reference-home/game-wine",
            "--env", "WINEDEBUG=-all", "--env", "LIBGL_ALWAYS_SOFTWARE=1",
            SESSION, "python3", "/baseline/extra_client.py"]


def exec_quote(value):
    """Quote one desktop Exec argument (not a shell command)."""
    value = str(value).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    # Desktop Entry string escaping is applied before Exec argument parsing.
    return '"' + value.replace("\\", "\\\\") + '"'


def shortcut_contents():
    command = exec_quote(sys.executable) + " " + exec_quote(ROOT / "launch.py")
    return ("[Desktop Entry]\nType=Application\nVersion=1.0\nName=GunZ (Local)\n"
            "Comment=Open GunZ login and its isolated local server\n"
            f"Exec={command}\nIcon=applications-games\nTerminal=true\nStartupNotify=false\n"
            "Categories=Game;ActionGame;\nX-GunZ-Launcher=true\nActions=Practice;\n\n"
            "[Desktop Action Practice]\nName=Mansion Practice\n"
            f"Exec={command} --practice\n")


def install_shortcuts():
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share")))
    paths = [data / "applications/gunz-local.desktop"]
    if shutil.which("xdg-user-dir"):
        desktop = checked_output(["xdg-user-dir", "DESKTOP"])
        if desktop and Path(desktop).is_absolute() and Path(desktop).resolve() != home.resolve():
            paths.append(Path(desktop) / "GunZ.desktop")
    elif (home / "Desktop").is_dir():
        paths.append(home / "Desktop/GunZ.desktop")
    # Check every destination before writing; never replace someone else's shortcut.
    for path in paths:
        if path.is_symlink() or (path.exists() and "X-GunZ-Launcher=true" not in path.read_text()):
            raise LauncherError(f"Refusing to replace an existing unrelated shortcut: {path}")
    contents = shortcut_contents()
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        path.chmod(0o755)
        print("Installed:", path)
    print("Use GunZ (Local) from the application menu or the desktop shortcut.")
    print("If the desktop asks, choose Allow Launching/Trust. No game was started.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--practice", action="store_true", help="Enter offline Mansion practice instead of login")
    modes.add_argument("--login", action="store_true", help="Open login/signup (the default)")
    modes.add_argument("--extra-client", action="store_true", help="Open another login client on the running local server")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--check", action="store_true", help="Check setup only; do not launch anything")
    operations.add_argument("--install-shortcut", action="store_true", help="Install desktop/menu entries without launching")
    parser.add_argument("--seconds", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.seconds is not None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.extra_client and (args.seconds is not None or args.install_shortcut):
        parser.error("--extra-client cannot be combined with --seconds or --install-shortcut")
    # Optional developer convenience; ordinary desktop launches use host Docker
    # directly and do not require VS Code, Flatpak, or flatpak-spawn.
    if Path("/.flatpak-info").exists():
        bridge = shutil.which("flatpak-spawn")
        if not bridge:
            raise LauncherError("Run play.sh from a host desktop terminal, outside the sandbox.")
        return subprocess.call([bridge, "--host", "python3", str(ROOT / "launch.py"), *argv])
    if sys.platform != "linux":
        raise LauncherError("This launcher is for the Linux/Wine setup; see baseline/README.md for the Windows executable.")
    if args.install_shortcut:
        return install_shortcuts()
    docker = docker_path()
    state = check_setup(docker)
    # Extra clients inherit the existing container's display and Xauthority.
    graphics = [] if args.extra_client else display_mounts(os.environ)
    if args.extra_client and state != "running":
        raise LauncherError("No running local session is available for --extra-client. Start GunZ normally first; no session was started or changed.")
    if args.check:
        print("READY: compiled client/server, runtime data, local Wine image, Docker and desktop display.")
        print("Existing session:", state or "none")
        selected_mode = "login/signup (default)"
        if args.extra_client:
            selected_mode = "extra login client on existing server"
        elif args.practice:
            selected_mode = "offline Mansion practice"
        print("Selected mode:", selected_mode)
        print("Check only: no container, client or server was started.")
        return 0
    if args.extra_client:
        print("Opening an extra login client on the existing local server. Use a DIFFERENT account.", flush=True)
        print("Keep the original client open: closing it stops the server and every extra client.", flush=True)
        print("Clients share settings/logs; software rendering uses more CPU with each window.", flush=True)
        return subprocess.call(extra_client_command(docker))
    if state:
        if state == "running":
            print("GunZ is already running. Use --extra-client to open another login window on this server; no second session was started.")
            return 0
        raise LauncherError(f"A {state} container named {SESSION} already exists. Inspect it in Docker before removing it; it was not changed.")
    print("Starting GunZ " + ("Mansion practice" if args.practice else "login/signup") + " and the local server.", flush=True)
    print("Closing the client stops this session's server; accounts and characters stay saved locally.", flush=True)
    return subprocess.call(launch_command(docker, args, graphics))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LauncherError, OSError, subprocess.TimeoutExpired) as error:
        print("GunZ:", error, file=sys.stderr)
        raise SystemExit(1)