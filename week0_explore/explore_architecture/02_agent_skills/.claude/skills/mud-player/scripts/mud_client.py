#!/usr/bin/env python3
"""Persistent raw-socket client for tbaMUD / CircleMUD-family servers.

Why not telnetlib: it was removed from the standard library in Python 3.13,
and this machine has no `telnet` or `tmux` binary either. So this talks raw
TCP and implements just enough of the telnet protocol (IAC negotiation) to
stay in sync with the server, plus strips ANSI color codes for readability.

Why a background daemon: a MUD session is stateful (you're logged into one
character on one TCP connection). Each shell call from an agent is a new
process, so the connection has to live in a small background daemon that
the CLI talks to over a local Unix socket -- one request/response per call.

Subcommands:
    start    [--host HOST] [--port PORT]           open the raw connection
    login    --name NAME --password PASSWORD       authenticate + enter game
    send     "<command text>"                       run one in-game command
    read     [--wait SECONDS]                        drain unsolicited output
    status
    stop                                             quit + close cleanly

Use --session-dir to run multiple concurrent sessions (e.g. two characters):
    mud_client.py --session-dir /tmp/mud-alice start --host localhost --port 4000
    mud_client.py --session-dir /tmp/mud-bob   start --host localhost --port 4000
"""
import argparse
import json
import os
import re
import signal
import socket
import sys
import threading
import time
from pathlib import Path

DEFAULT_STATE_ROOT = Path("/tmp/mud-skill")

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")
GAME_PROMPT_RE = re.compile(r"\d+H \d+M \d+V.*>\s*$")
LOGIN_PROMPT_RE = re.compile(
    r"(wish to be known\?|Password:|PRESS RETURN|Make your choice:|"
    r"Yes or No|\(Y/N\)\?|Did I get that right|Wrong password|Illegal password)",
    re.I,
)


def state_dir(args):
    if args.session_dir:
        d = Path(args.session_dir)
    else:
        d = DEFAULT_STATE_ROOT / f"{args.host}_{args.port}"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TelnetFilter:
    """Strips IAC negotiation out of a byte stream and builds refusal replies.

    Assumes an IAC sequence never splits across two recv() chunks -- true in
    practice for a local dev MUD, not guaranteed by the telnet spec in general.
    """

    def feed(self, data: bytes):
        out, replies = bytearray(), bytearray()
        i, n = 0, len(data)
        while i < n:
            b = data[i]
            if b != IAC:
                out.append(b)
                i += 1
                continue
            if i + 1 >= n:
                break
            cmd = data[i + 1]
            if cmd in (WILL, WONT, DO, DONT):
                if i + 2 >= n:
                    break
                opt = data[i + 2]
                if cmd == WILL:
                    replies += bytes([IAC, DONT, opt])
                elif cmd == DO:
                    replies += bytes([IAC, WONT, opt])
                i += 3
            elif cmd == SB:
                j = data.find(bytes([IAC, SE]), i)
                if j == -1:
                    break
                i = j + 2
            elif cmd == IAC:
                out.append(IAC)
                i += 2
            else:
                i += 2
        return bytes(out), bytes(replies)


class Session:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(None)
        self.filter = TelnetFilter()
        self.buf = []
        self.delivered = 0
        self.buf_lock = threading.Lock()
        self.new_data = threading.Event()
        self.alive = True
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while True:
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            text, replies = self.filter.feed(chunk)
            if replies:
                try:
                    self.sock.sendall(replies)
                except OSError:
                    pass
            if text:
                clean = ANSI_RE.sub(b"", text).replace(b"\r\n", b"\n").replace(b"\r", b"")
                with self.buf_lock:
                    self.buf.append(clean.decode("latin-1"))
                self.new_data.set()
        self.alive = False
        self.new_data.set()

    def send_line(self, text):
        self.sock.sendall(text.encode("latin-1", errors="replace") + b"\r\n")

    def drain(self, quiet=0.6, max_wait=6.0):
        """Return text appended since the last drain.

        Stops as soon as the tail looks like a known prompt (fast path -- this
        is what makes login reliable despite the server's telnet-negotiation
        delays), otherwise falls back to a plain quiet-period timeout.
        """
        start = last_change = time.time()
        last_len = len(self.buf)
        while True:
            with self.buf_lock:
                cur_len = len(self.buf)
            if cur_len != last_len:
                last_len = cur_len
                last_change = time.time()
                with self.buf_lock:
                    tail = "".join(self.buf[max(0, cur_len - 3):cur_len])
                if GAME_PROMPT_RE.search(tail) or LOGIN_PROMPT_RE.search(tail):
                    break
            if not self.alive:
                break
            now = time.time()
            if now - last_change >= quiet or now - start >= max_wait:
                break
            self.new_data.wait(timeout=0.1)
            self.new_data.clear()
        with self.buf_lock:
            text = "".join(self.buf[self.delivered:])
            self.delivered = len(self.buf)
        return text


def run_daemon(host, port, sockpath):
    session = Session(host, port)
    if os.path.exists(sockpath):
        os.remove(sockpath)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sockpath)
    srv.listen(8)
    stop_flag = threading.Event()

    def handle(conn):
        try:
            f = conn.makefile("rwb")
            line = f.readline()
            if not line:
                return
            req = json.loads(line.decode("utf-8"))
            action = req.get("action")
            if action == "send":
                session.send_line(req.get("text", ""))
                text = session.drain(quiet=req.get("quiet", 0.8), max_wait=req.get("max_wait", 6.0))
                resp = {"ok": True, "text": text, "alive": session.alive}
            elif action == "read":
                text = session.drain(quiet=req.get("quiet", 0.5), max_wait=req.get("max_wait", 1.5))
                resp = {"ok": True, "text": text, "alive": session.alive}
            elif action == "status":
                with session.buf_lock:
                    pending = len(session.buf) - session.delivered
                resp = {"ok": True, "alive": session.alive, "pending_chunks": pending}
            elif action in ("quit", "shutdown"):
                if action == "quit" and session.alive:
                    try:
                        session.send_line("quit")
                        text = session.drain(quiet=0.8, max_wait=3.0)
                    except OSError:
                        text = ""
                else:
                    text = ""
                resp = {"ok": True, "text": text}
                stop_flag.set()
            else:
                resp = {"ok": False, "error": f"unknown action {action!r}"}
            f.write((json.dumps(resp) + "\n").encode("utf-8"))
            f.flush()
        finally:
            conn.close()
        if stop_flag.is_set():
            try:
                session.sock.close()
            except OSError:
                pass
            try:
                srv.close()
            except OSError:
                pass
            try:
                os.remove(sockpath)
            except OSError:
                pass
            os._exit(0)

    while True:
        conn, _ = srv.accept()
        handle(conn)


def rpc(sockpath, action, timeout=8.0, **kwargs):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(sockpath))
    req = {"action": action, **kwargs}
    s.sendall((json.dumps(req) + "\n").encode("utf-8"))
    f = s.makefile("rb")
    line = f.readline()
    s.close()
    if not line:
        return {"ok": False, "error": "empty response from daemon"}
    return json.loads(line.decode("utf-8"))


def daemon_alive(sockpath):
    if not sockpath.exists():
        return False
    try:
        resp = rpc(sockpath, "status", timeout=1.5)
        return resp.get("ok", False)
    except OSError:
        return False


def spawn_daemon(host, port, sockpath, pidpath, logpath):
    import subprocess

    if sockpath.exists():
        sockpath.unlink()
    with open(logpath, "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--host", host, "--port", str(port), "_daemon", "--sock", str(sockpath)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    pidpath.write_text(str(proc.pid))
    for _ in range(50):
        if sockpath.exists() and daemon_alive(sockpath):
            return
        time.sleep(0.1)
    raise RuntimeError(f"daemon did not come up; check log at {logpath}")


def cmd_start(args):
    d = state_dir(args)
    sockpath, pidpath, logpath = d / "control.sock", d / "daemon.pid", d / "daemon.log"

    if daemon_alive(sockpath):
        print(f"Already connected ({d}). Use `login`, `send`/`read`, or `stop` first to restart.")
        return

    open(logpath, "w").close()
    spawn_daemon(args.host, args.port, sockpath, pidpath, logpath)

    # The server has a real gap (client-detection negotiation) between its first
    # flushed line and the rest of the banner, so use a generous quiet window here.
    banner = rpc(sockpath, "read", quiet=1.5, max_wait=5.0)["text"]
    print(banner, end="" if banner.endswith("\n") else "\n")


def cmd_login(args):
    d = state_dir(args)
    sockpath, logpath, sessionpath = d / "control.sock", d / "daemon.log", d / "session.json"

    if not daemon_alive(sockpath):
        print("[login] no active connection, starting one first...")
        cmd_start(args)

    # Make sure the name prompt is fully drained before answering it -- if `start`
    # left any of the banner unread, a premature `send` here would capture that
    # stale leftover instead of the real response to our name.
    leftover = rpc(sockpath, "read", quiet=1.5, max_wait=5.0)["text"]
    if leftover:
        print(leftover, end="")

    r = rpc(sockpath, "send", text=args.name, max_wait=4.0)["text"]
    print(r, end="")
    if "Did I get that right" in r or "New character" in r:
        rpc(sockpath, "shutdown")
        print(f"\n[login] '{args.name}' does not exist yet on this server -- aborting rather than "
              f"auto-creating a new character. Create it manually first, then retry.", file=sys.stderr)
        sys.exit(1)
    if "Password:" not in r:
        rpc(sockpath, "shutdown")
        print(f"\n[login] unexpected response to name, aborting. See log: {logpath}", file=sys.stderr)
        sys.exit(1)

    r = rpc(sockpath, "send", text=args.password, max_wait=4.0)["text"]
    print(r, end="")
    if "Wrong password" in r or "Illegal password" in r:
        rpc(sockpath, "shutdown")
        print("\n[login] login failed (wrong password).", file=sys.stderr)
        sys.exit(1)

    if not (GAME_PROMPT_RE.search(r) or "Exits:" in r):
        # Normal path: a linkless character that reconnects silently skips straight
        # back into the game right after the password, with no MOTD/menu at all.
        if "PRESS RETURN" not in r:
            rpc(sockpath, "shutdown")
            print(f"\n[login] unexpected response to password, aborting. See log: {logpath}", file=sys.stderr)
            sys.exit(1)

        r = rpc(sockpath, "send", text="", max_wait=4.0)["text"]
        print(r, end="")

        r = rpc(sockpath, "send", text="1", max_wait=5.0)["text"]
        print(r, end="")
        if "Yes or No" in r or re.search(r"already.*(logged|connect)", r, re.I):
            r = rpc(sockpath, "send", text="yes", max_wait=5.0)["text"]
            print(r, end="")

    if GAME_PROMPT_RE.search(r) or "Exits:" in r:
        sessionpath.write_text(json.dumps({"name": args.name, "host": args.host, "port": args.port}))
        print(f"\n[login] Logged in as {args.name}.")
    else:
        print(f"\n[login] Sequence finished but the result doesn't look like the game prompt -- "
              f"check the transcript above. Session is still open; try `send` manually or `stop` to clean up.",
              file=sys.stderr)


def _require_daemon(sockpath):
    if not daemon_alive(sockpath):
        print("Not connected. Run `start` (and `login`) first.", file=sys.stderr)
        sys.exit(1)


def cmd_send(args):
    d = state_dir(args)
    sockpath = d / "control.sock"
    _require_daemon(sockpath)
    resp = rpc(sockpath, "send", text=args.text, max_wait=args.wait)
    print(resp["text"], end="")
    if not resp["text"].endswith("\n"):
        print()


def cmd_read(args):
    d = state_dir(args)
    sockpath = d / "control.sock"
    _require_daemon(sockpath)
    resp = rpc(sockpath, "read", max_wait=args.wait)
    print(resp["text"], end="")


def cmd_status(args):
    d = state_dir(args)
    sockpath = d / "control.sock"
    sessionpath = d / "session.json"
    if not daemon_alive(sockpath):
        print("not connected")
        return
    resp = rpc(sockpath, "status")
    who = json.loads(sessionpath.read_text())["name"] if sessionpath.exists() else "(not logged in)"
    print(f"connected as {who} ({args.host}:{args.port}), alive={resp['alive']}, pending_chunks={resp['pending_chunks']}")


def cmd_stop(args):
    d = state_dir(args)
    sockpath, pidpath, sessionpath = d / "control.sock", d / "daemon.pid", d / "session.json"

    if daemon_alive(sockpath):
        resp = rpc(sockpath, "quit", timeout=6.0)
        print(resp.get("text", ""), end="")
        print("\n[stop] disconnected cleanly.")
    else:
        print("[stop] no active connection.")

    if pidpath.exists():
        try:
            os.kill(int(pidpath.read_text()), signal.SIGTERM)
        except (ValueError, ProcessLookupError):
            pass
        pidpath.unlink(missing_ok=True)
    sockpath.unlink(missing_ok=True)
    sessionpath.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=4000)
    p.add_argument("--session-dir", default=None, help="override the state directory (for running multiple concurrent sessions)")
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("start", help="open the raw connection to the MUD (no login yet)")
    st.set_defaults(func=cmd_start)

    lg = sub.add_parser("login", help="authenticate and enter the game")
    lg.add_argument("--name", required=True)
    lg.add_argument("--password", required=True)
    lg.set_defaults(func=cmd_login)

    s = sub.add_parser("send", help="send one command line, return the response text")
    s.add_argument("text")
    s.add_argument("--wait", type=float, default=6.0, help="max seconds to wait for the response to settle")
    s.set_defaults(func=cmd_send)

    r = sub.add_parser("read", help="drain any unsolicited output (tells, combat spam) without sending anything")
    r.add_argument("--wait", type=float, default=1.5)
    r.set_defaults(func=cmd_read)

    stt = sub.add_parser("status", help="check whether a session is active")
    stt.set_defaults(func=cmd_status)

    sp = sub.add_parser("stop", help="quit the game and close the session cleanly (force-kills if unresponsive)")
    sp.set_defaults(func=cmd_stop)

    dmn = sub.add_parser("_daemon", help=argparse.SUPPRESS)
    dmn.add_argument("--sock", required=True)
    dmn.set_defaults(func=None)

    args = p.parse_args()
    if args.cmd == "_daemon":
        run_daemon(args.host, args.port, args.sock)
        return
    args.func(args)


if __name__ == "__main__":
    main()
