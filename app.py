# -*- coding: utf-8 -*-
"""TCP 송수신 테스트 도구.

운영 소켓(SK_DELIMITER_TYPE)과 같이 본문 밖에 구분자를 붙여 보낸다.
LINE=CR LF, NULL=0x00, STX/ETX=앞에 0x02 뒤에 0x03, CR=0x0D, LF=0x0A.
구분자를 한 번 지정하면 송신 문자열에 다시 입력하지 않아도 된다.
"""

import json
import os
import queue
import re
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import encodings.ascii
import encodings.utf_8

APP_TITLE = "TCP Socket Tool"
MAX_BUFFER = 1024 * 1024
MAX_LOG_LINES = 4000

DELIMITERS = [
    ("LINE (CR LF)", b"", b"\r\n"),
    ("NULL (0x00)", b"", b"\x00"),
    ("STX/ETX", b"\x02", b"\x03"),
    ("CR (0x0D)", b"", b"\x0d"),
    ("LF (0x0A)", b"", b"\x0a"),
    ("없음", b"", b""),
    ("직접입력", None, None),
]
DELIMITER_NAMES = [name for name, _prefix, _suffix in DELIMITERS]

CHARSETS = {
    "UTF-8": "utf-8",
    "ASCII": "ascii",
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(app_dir(), "config.json")


def messages_path():
    return os.path.join(app_dir(), "messages.json")


def to_decimal(data):
    return " ".join(str(b) for b in data)


def to_hex(data):
    return " ".join(f"{b:02X}" for b in data)


def _parse_byte_token(token):
    text = token.strip()
    if not text:
        raise ValueError("빈 값")
    try:
        if text.lower().startswith("0x"):
            value = int(text, 16)
        elif re.search(r"[A-Fa-f]", text) and re.fullmatch(r"[0-9A-Fa-f]+", text):
            value = int(text, 16)
        else:
            value = int(text, 10)
    except ValueError as exc:
        raise ValueError(f"숫자가 아닙니다: {token}") from exc
    if not 0 <= value <= 255:
        raise ValueError(f"0~255 범위가 아닙니다: {token}")
    return value


def parse_byte_text(text):
    raw = text.replace(",", " ").replace("\n", " ").replace("\r", " ").strip()
    if not raw:
        return b""
    return bytes(_parse_byte_token(part) for part in raw.split())


def parse_custom_delimiter(text, encoding):
    raw = text.strip()
    if not raw:
        return b""
    if raw in (r"\r\n", r"\n", r"\r", r"\0", r"\x00"):
        return raw.encode("utf-8").decode("unicode_escape").encode("latin1")
    if "\\" in raw and " " not in raw and not raw.lower().startswith("0x"):
        try:
            return raw.encode("utf-8").decode("unicode_escape").encode("latin1")
        except (UnicodeError, ValueError):
            pass
    compact = raw.replace(" ", "")
    if (
        " " not in raw
        and re.fullmatch(r"(?i)[0-9a-f]{4,}", compact)
        and len(compact) % 2 == 0
        and re.search(r"[A-Fa-f]", compact)
    ):
        return bytes(int(compact[i:i + 2], 16) for i in range(0, len(compact), 2))
    parts = raw.replace(",", " ").split()
    try:
        if len(parts) == 1 and not _looks_like_byte(parts[0]):
            return raw.encode(encoding)
        return bytes(_parse_byte_token(part) for part in parts)
    except ValueError:
        return raw.encode(encoding)


def _looks_like_byte(token):
    if token.lower().startswith("0x"):
        return True
    if re.fullmatch(r"[0-9A-Fa-f]+", token) and re.search(r"[A-Fa-f]", token):
        return True
    return token.isdigit() and 0 <= int(token) <= 255


def resolve_delimiter(name, custom, encoding):
    """(앞에 붙는 바이트, 뒤에 붙는 바이트)를 반환한다."""
    for label, prefix, suffix in DELIMITERS:
        if label == name:
            if prefix is None:
                return b"", parse_custom_delimiter(custom, encoding)
            return prefix, suffix
    return b"", b"\x00"


def apply_framing(payload, prefix, suffix, auto):
    if not auto:
        return payload
    framed = payload
    if prefix and not framed.startswith(prefix):
        framed = prefix + framed
    if suffix and not framed.endswith(suffix):
        framed = framed + suffix
    return framed


def take_frames(buf, prefix, suffix):
    """완성된 프레임을 꺼낸다. STX/ETX는 앞 구분자부터 뒷 구분자까지 한 건이다."""
    frames = []
    if not prefix and not suffix:
        if buf:
            frames.append((bytes(buf), True))
            buf.clear()
        return frames
    if not prefix:
        while True:
            index = buf.find(suffix)
            if index < 0:
                break
            end = index + len(suffix)
            frames.append((bytes(buf[:end]), True))
            del buf[:end]
        if len(buf) > MAX_BUFFER:
            frames.append((bytes(buf), False))
            buf.clear()
        return frames
    while True:
        start = buf.find(prefix)
        if start < 0:
            if len(buf) > MAX_BUFFER:
                frames.append((bytes(buf), False))
                buf.clear()
            break
        if start > 0:
            frames.append((bytes(buf[:start]), False))
            del buf[:start]
        end_rel = buf.find(suffix, len(prefix))
        if end_rel < 0:
            if len(buf) > MAX_BUFFER:
                frames.append((bytes(buf), False))
                buf.clear()
            break
        end = end_rel + len(suffix)
        frames.append((bytes(buf[:end]), True))
        del buf[:end]
    return frames


def decode_text(data, encoding):
    return data.decode(encoding, errors="replace")


def looks_like_text(data, encoding):
    if not data:
        return True
    try:
        text = data.decode(encoding)
    except UnicodeError:
        return False
    for char in text:
        code = ord(char)
        if char == "\ufffd" or (code < 32 and char != "\t"):
            return False
    return True


def frame_body(frame, prefix, suffix, complete):
    if not complete:
        return frame
    body = frame
    if prefix and body.startswith(prefix):
        body = body[len(prefix):]
    if suffix and body.endswith(suffix):
        body = body[:-len(suffix)]
    return body


class Engine:
    def __init__(self, events):
        self.events = events
        self.mode = None
        self.prefix = b""
        self.suffix = b"\x00"
        self.encoding = "utf-8"
        self.reply_on = False
        self.reply_text = ""
        self.reply_auto = True
        self._lock = threading.Lock()
        self._gen = 0
        self._running = False
        self._server = None
        self._peers = {}

    def set_framing(self, prefix, suffix, encoding):
        with self._lock:
            self.prefix = prefix
            self.suffix = suffix
            self.encoding = encoding

    def set_reply(self, enabled, text, auto):
        with self._lock:
            self.reply_on = bool(enabled)
            self.reply_text = text or ""
            self.reply_auto = bool(auto)

    def _framing(self):
        with self._lock:
            return self.prefix, self.suffix, self.encoding

    def _reply_settings(self):
        with self._lock:
            return self.reply_on, self.reply_text, self.reply_auto

    def start_server(self, host, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.listen(50)
            sock.settimeout(0.4)
        except OSError:
            sock.close()
            raise
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._running = True
            self.mode = "SERVER"
            self._server = sock
            self._peers = {}
        threading.Thread(
            target=self._accept_loop, args=(sock, gen), name="tcp-accept", daemon=True
        ).start()
        return gen

    def start_client(self, host, port):
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._running = True
            self.mode = "CLIENT"
            self._peers = {}
        threading.Thread(
            target=self._connect, args=(host, port, gen), name="tcp-connect", daemon=True
        ).start()
        return gen

    def stop(self):
        with self._lock:
            old = self._gen
            self._gen += 1
            self._running = False
            server = self._server
            self._server = None
            peers = list(self._peers.values())
            self._peers = {}
        if server is not None:
            _close_socket(server)
        for peer in peers:
            peer.alive = False
            _close_socket(peer.sock)
        self.events.put(("status", "대기"))
        self.events.put(("peers", []))
        self.events.put(("closed", old))

    def send(self, targets, data):
        with self._lock:
            if targets == "ALL" or targets is None:
                peers = list(self._peers.values())
            elif isinstance(targets, str):
                peer = self._peers.get(targets)
                peers = [peer] if peer is not None else []
            else:
                peers = [self._peers[name] for name in targets if name in self._peers]
        if not peers:
            return 0, "연결된 대상이 없습니다"
        ok = 0
        errors = []
        for peer in peers:
            try:
                peer.sock.sendall(data)
                ok += 1
            except OSError as exc:
                errors.append(f"{peer.label}: {exc}")
                peer.alive = False
                _close_socket(peer.sock)
        return ok, "; ".join(errors)

    def _accept_loop(self, server, gen):
        try:
            bound = server.getsockname()
            self.events.put(("log", "channelRegistered"))
            self.events.put(("log", f"channelActive listen {bound[0]}:{bound[1]}"))
            self.events.put(("status", f"SERVER {bound[0]}:{bound[1]}  연결 0"))
            while self._current(gen):
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    if self._current(gen):
                        self.events.put(("log", f"exceptionCaught:{exc}"))
                    break
                if not self._current(gen):
                    _close_socket(conn)
                    break
                self._attach(conn, addr, gen)
        finally:
            _close_socket(server)
            with self._lock:
                if self._server is server:
                    self._server = None
            self.events.put(("log", "channelInactive"))
            self.events.put(("log", "channelUnregistered"))

    def _connect(self, host, port, gen):
        self.events.put(("status", f"연결중 {host}:{port}"))
        try:
            sock = socket.create_connection((host, port), timeout=5)
        except OSError as exc:
            self.events.put(("log", f"exceptionCaught:{exc}"))
            with self._lock:
                current = self._gen == gen
                if current:
                    self._running = False
            if current:
                self.events.put(("status", "대기"))
                self.events.put(("closed", gen))
            return
        if not self._current(gen):
            _close_socket(sock)
            return
        self._attach(sock, sock.getpeername(), gen)

    def _attach(self, sock, addr, gen):
        _prepare_socket(sock)
        label = self._unique_label(addr)
        peer = Peer(sock, label)
        with self._lock:
            if not self._current_locked(gen):
                _close_socket(sock)
                return None
            self._peers[label] = peer
            labels = list(self._peers.keys())
            listen = None
            if self._server is not None:
                try:
                    listen = self._server.getsockname()
                except OSError:
                    listen = None
        self.events.put(("peers", labels))
        if self.mode == "SERVER" and listen is not None:
            self.events.put(("status", f"SERVER {listen[0]}:{listen[1]}  연결 {len(labels)}"))
        elif self.mode == "CLIENT":
            self.events.put(("status", f"CLIENT {label}"))
        threading.Thread(
            target=self._read_loop, args=(peer, gen), name=f"tcp-read-{label}", daemon=True
        ).start()
        return peer

    def _read_loop(self, peer, gen):
        # 클라이언트 연결 스레드가 직접 읽기를 호출하면 중복 스레드가 생기지 않게 한다.
        if getattr(peer, "reader_started", False):
            return
        peer.reader_started = True
        self.events.put(("log", "channelRegistered"))
        self.events.put(("log", f"channelActive {peer.label}"))
        try:
            while peer.alive and self._current(gen):
                try:
                    data = peer.sock.recv(8192)
                except socket.timeout:
                    continue
                except OSError as exc:
                    if peer.alive and self._current(gen):
                        self.events.put(("log", f"exceptionCaught:{exc}"))
                    break
                if not data:
                    break
                self._on_bytes(peer, data)
        finally:
            peer.alive = False
            _close_socket(peer.sock)
            self._remove_peer(peer)
            if peer.buf:
                self.events.put((
                    "log",
                    f"channelRead {self._who(peer)}Byte:{to_decimal(peer.buf)} (구분자 대기 중 연결 종료)",
                ))
            self.events.put(("log", f"channelInactive {peer.label}"))
            self.events.put(("log", "channelUnregistered"))
            if self.mode == "CLIENT":
                with self._lock:
                    unexpected = self._gen == gen and self._running
                    if unexpected:
                        self._running = False
                self.events.put(("status", "대기"))
                self.events.put(("peers", []))
                if unexpected:
                    self.events.put(("closed", gen))

    def _on_bytes(self, peer, data):
        prefix, suffix, encoding = self._framing()
        # 구분자가 올 때까지 쌓아 두면 상대가 NULL을 안 붙인 데이터는 화면에 안 나온다.
        # 소켓에서 읽힌 바이트는 바로 로그에 남긴다.
        self._publish_frame(peer, data, True, prefix, suffix, encoding)
        self._reply_now(peer, data, prefix, suffix, encoding)

    def _reply_now(self, peer, frame, prefix, suffix, encoding):
        enabled, custom, auto = self._reply_settings()
        if not enabled:
            return
        if custom == "":
            payload = frame
            shown = decode_text(frame_body(frame, prefix, suffix, True), encoding)
        else:
            try:
                body = custom.encode(encoding)
            except UnicodeEncodeError:
                self.events.put(("log", f"exceptionCaught:{encoding} 로 변환할 수 없는 응답입니다"))
                return
            payload = apply_framing(body, prefix, suffix, auto)
            shown = custom
        shown = "".join(ch for ch in shown.replace("\r", "").replace("\n", "") if ch != "\x00")
        now = time.monotonic()
        guard = getattr(peer, "reply_guard", None)
        if guard and guard[0] == frame and now - guard[1] < 0.5:
            return
        try:
            peer.sock.sendall(payload)
        except OSError as exc:
            self.events.put(("log", f"exceptionCaught:{peer.label} 응답 송신 실패 {exc}"))
            return
        peer.reply_guard = (payload, now)
        self.events.put(("log", f"send {peer.label} Byte:{to_decimal(payload)}"))
        self.events.put(("log", f"send {peer.label} String:{shown}"))

    def _publish_frame(self, peer, frame, complete, prefix, suffix, encoding):
        body = frame_body(frame, prefix, suffix, complete)
        text = decode_text(body, encoding)
        shown = "".join(ch for ch in text.replace("\r", "").replace("\n", "") if ch != "\x00")
        who = self._who(peer)
        self.events.put(("log", f"channelRead {who}Byte:{to_decimal(frame)}"))
        self.events.put(("log", f"channelRead {who}String:{shown}"))
        if complete:
            self.events.put(("log", "channelReadComplete"))
        else:
            self.events.put(("log", "channelRead (구분자 없이 버퍼 한도를 넘어 원문을 출력)"))
        self.events.put(("rx", {
            "label": peer.label,
            "frame": frame,
            "text": shown,
            "body": body,
            "binary": not looks_like_text(body, encoding),
        }))

    def _who(self, peer):
        if self.mode == "SERVER":
            return peer.label + " "
        return ""

    def _remove_peer(self, peer):
        with self._lock:
            current = self._peers.get(peer.label)
            if current is peer:
                del self._peers[peer.label]
            labels = list(self._peers.keys())
            listen = None
            if self._server is not None:
                try:
                    listen = self._server.getsockname()
                except OSError:
                    listen = None
            mode = self.mode
        self.events.put(("peers", labels))
        if mode == "SERVER" and listen is not None:
            self.events.put(("status", f"SERVER {listen[0]}:{listen[1]}  연결 {len(labels)}"))

    def _unique_label(self, addr):
        base = f"{addr[0]}:{addr[1]}"
        label = base
        number = 2
        with self._lock:
            while label in self._peers:
                label = f"{base}#{number}"
                number += 1
        return label

    def _current(self, gen):
        with self._lock:
            return self._current_locked(gen)

    def _current_locked(self, gen):
        return self._running and self._gen == gen


class Peer:
    def __init__(self, sock, label):
        self.sock = sock
        self.label = label
        self.buf = bytearray()
        self.alive = True
        self.reader_started = False


def _prepare_socket(sock):
    sock.settimeout(0.4)
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def _close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class App:
    def __init__(self):
        self.events = queue.Queue()
        self.engine = Engine(self.events)
        self.connected = False
        self.session = None
        self.rx_items = []
        self._build()
        self._load_config()
        self._load_templates()
        self._push_framing()
        self.root.after(50, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1040x700")
        self.root.minsize(920, 600)
        self.root.configure(bg="#f0f0f0")

        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TLabel", font=("Malgun Gothic", 9))
        style.configure("TButton", font=("Malgun Gothic", 9), padding=(8, 4))
        style.configure("Send.TButton", font=("Malgun Gothic", 12, "bold"), padding=(8, 12))
        style.configure("TCheckbutton", font=("Malgun Gothic", 9))

        top = ttk.Frame(self.root, padding=(8, 8, 8, 2))
        top.pack(fill="x")

        ttk.Label(top, text="TCP").grid(row=0, column=0, padx=(0, 6))
        self.mode = tk.StringVar(value="SERVER")
        self.mode_box = ttk.Combobox(
            top, textvariable=self.mode, values=("SERVER", "CLIENT"),
            state="readonly", width=10, font=("Malgun Gothic", 9),
        )
        self.mode_box.grid(row=0, column=1, padx=(0, 10))
        self.mode_box.bind("<<ComboboxSelected>>", self._on_mode)

        ttk.Label(top, text="IP / PORT").grid(row=0, column=2, padx=(0, 4))
        self.ip = tk.StringVar(value="0.0.0.0")
        self.ip_entry = ttk.Entry(top, textvariable=self.ip, width=16, font=("Consolas", 10))
        self.ip_entry.grid(row=0, column=3)
        ttk.Label(top, text="/").grid(row=0, column=4, padx=4)
        self.port = tk.StringVar(value="35000")
        self.port_entry = ttk.Entry(top, textvariable=self.port, width=8, font=("Consolas", 10))
        self.port_entry.grid(row=0, column=5, padx=(0, 10))

        self.bind_btn = ttk.Button(top, text="BIND", width=10, command=self._toggle)
        self.bind_btn.grid(row=0, column=6, padx=(0, 4))
        ttk.Button(top, text="CLEAN", width=10, command=self._clean).grid(row=0, column=7)

        opt = ttk.Frame(self.root, padding=(8, 2, 8, 4))
        opt.pack(fill="x")
        ttk.Label(opt, text="DELIMITER").grid(row=0, column=0, padx=(0, 4))
        self.delim_name = tk.StringVar(value="NULL (0x00)")
        self.delim_box = ttk.Combobox(
            opt, textvariable=self.delim_name, values=DELIMITER_NAMES,
            state="readonly", width=16, font=("Malgun Gothic", 9),
        )
        self.delim_box.grid(row=0, column=1, padx=(0, 4))
        self.delim_box.bind("<<ComboboxSelected>>", self._on_delim)
        self.custom = tk.StringVar()
        self.custom_entry = ttk.Entry(opt, textvariable=self.custom, width=18, font=("Consolas", 10))
        self.custom_entry.grid(row=0, column=2, padx=(0, 8))
        self.custom_entry.configure(state="disabled")
        self.custom.trace_add("write", lambda *_: self._push_framing())

        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="송신 시 자동추가", variable=self.auto).grid(row=0, column=3, padx=(0, 12))

        ttk.Label(opt, text="문자셋").grid(row=0, column=4, padx=(0, 4))
        self.charset = tk.StringVar(value="UTF-8")
        charset_box = ttk.Combobox(
            opt, textvariable=self.charset, values=tuple(CHARSETS.keys()),
            state="readonly", width=8, font=("Malgun Gothic", 9),
        )
        charset_box.grid(row=0, column=5, padx=(0, 10))
        charset_box.bind("<<ComboboxSelected>>", lambda _e: self._push_framing())

        self.reply_on = tk.BooleanVar(value=False)
        self.reply_text = tk.StringVar()
        ttk.Checkbutton(opt, text="수신 시 응답", variable=self.reply_on).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Entry(opt, textvariable=self.reply_text, width=36, font=("Malgun Gothic", 10)).grid(
            row=1, column=2, columnspan=3, sticky="ew", padx=(0, 8), pady=(4, 0)
        )
        ttk.Label(opt, text="비우면 받은 바이트 그대로 그 소켓에 송신").grid(
            row=1, column=5, columnspan=3, sticky="w", pady=(4, 0)
        )
        self.reply_on.trace_add("write", lambda *_: self._push_reply())
        self.reply_text.trace_add("write", lambda *_: self._push_reply())
        self.auto.trace_add("write", lambda *_: self._push_reply())

        self.status = tk.StringVar(value="대기")
        ttk.Label(self.root, textvariable=self.status, padding=(8, 0, 8, 2)).pack(anchor="w")

        log_wrap = ttk.Frame(self.root, padding=(8, 0, 8, 4))
        log_wrap.pack(fill="both", expand=True)
        self.log = tk.Text(
            log_wrap, height=14, wrap="none", bg="white", relief="solid", bd=1,
            font=("Consolas", 10), state="disabled",
        )
        log_y = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log.yview)
        log_x = ttk.Scrollbar(log_wrap, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=log_y.set, xscrollcommand=log_x.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        log_y.grid(row=0, column=1, sticky="ns")
        log_x.grid(row=1, column=0, sticky="ew")
        log_wrap.rowconfigure(0, weight=1)
        log_wrap.columnconfigure(0, weight=1)

        bottom = ttk.Frame(self.root, padding=(8, 2, 8, 8))
        bottom.pack(fill="both", expand=True)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        left = ttk.Frame(bottom)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="전문").grid(row=0, column=0, sticky="w")
        list_wrap = ttk.Frame(left)
        list_wrap.grid(row=1, column=0, sticky="nsew")
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)
        self.msg_list = tk.Listbox(
            list_wrap, width=28, bg="white", relief="solid", bd=1,
            font=("Malgun Gothic", 9), activestyle="dotbox",
        )
        msg_y = ttk.Scrollbar(list_wrap, orient="vertical", command=self.msg_list.yview)
        self.msg_list.configure(yscrollcommand=msg_y.set)
        self.msg_list.grid(row=0, column=0, sticky="nsew")
        msg_y.grid(row=0, column=1, sticky="ns")
        self.msg_list.bind("<Double-Button-1>", lambda _e: self._load_selected())
        self.msg_list.bind("<Delete>", lambda _e: self._delete_selected())
        btn_row = ttk.Frame(left)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(btn_row, text="보관", width=6, command=self._keep_current).pack(side="left", padx=(0, 2))
        ttk.Button(btn_row, text="불러오기", width=8, command=self._load_selected).pack(side="left", padx=(0, 2))
        ttk.Button(btn_row, text="삭제", width=6, command=self._delete_selected).pack(side="left")

        center = ttk.Frame(bottom)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        self.notebook = ttk.Notebook(center)
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        string_tab = ttk.Frame(self.notebook, padding=4)
        byte_tab = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(string_tab, text="STRING")
        self.notebook.add(byte_tab, text="BYTE")
        self.string_tab = string_tab
        self.byte_tab = byte_tab

        self.string_hint = tk.StringVar(value="본문만 입력합니다. 송신 시 구분자가 자동으로 붙습니다.  Ctrl+Enter 송신")
        ttk.Label(string_tab, textvariable=self.string_hint).pack(anchor="w")
        string_wrap = ttk.Frame(string_tab)
        string_wrap.pack(fill="both", expand=True, pady=(4, 0))
        string_wrap.rowconfigure(0, weight=1)
        string_wrap.columnconfigure(0, weight=1)
        self.string_text = tk.Text(string_wrap, wrap="word", font=("Malgun Gothic", 11), undo=True, bg="white")
        string_y = ttk.Scrollbar(string_wrap, orient="vertical", command=self.string_text.yview)
        self.string_text.configure(yscrollcommand=string_y.set)
        self.string_text.grid(row=0, column=0, sticky="nsew")
        string_y.grid(row=0, column=1, sticky="ns")
        self.string_text.bind("<Control-Return>", lambda _e: self._send())

        ttk.Label(byte_tab, text="10진수(45 0) 또는 16진수(2D 00, 0x2D). 구분자도 여기에 직접 넣을 수 있습니다.  Ctrl+Enter 송신").pack(anchor="w")
        byte_wrap = ttk.Frame(byte_tab)
        byte_wrap.pack(fill="both", expand=True, pady=(4, 0))
        byte_wrap.rowconfigure(0, weight=1)
        byte_wrap.columnconfigure(0, weight=1)
        self.byte_text = tk.Text(byte_wrap, wrap="word", font=("Consolas", 11), undo=True, bg="white")
        byte_y = ttk.Scrollbar(byte_wrap, orient="vertical", command=self.byte_text.yview)
        self.byte_text.configure(yscrollcommand=byte_y.set)
        self.byte_text.grid(row=0, column=0, sticky="nsew")
        byte_y.grid(row=0, column=1, sticky="ns")
        self.byte_text.bind("<Control-Return>", lambda _e: self._send())
        self.byte_text.bind("<KeyRelease>", lambda _e: self._refresh_preview())
        self.preview = tk.StringVar(value="HEX: (비어 있음)")
        ttk.Label(byte_tab, textvariable=self.preview).pack(anchor="w", pady=(4, 0))

        right = ttk.Frame(bottom)
        right.grid(row=0, column=2, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="대상  (Ctrl+클릭으로 여러 곳)").grid(row=0, column=0, columnspan=2, sticky="w")
        target_wrap = ttk.Frame(right)
        target_wrap.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(2, 4))
        target_wrap.rowconfigure(0, weight=1)
        target_wrap.columnconfigure(0, weight=1)
        self.target_list = tk.Listbox(
            target_wrap, height=6, width=24, selectmode="extended", exportselection=False,
            bg="white", relief="solid", bd=1, font=("Consolas", 9), activestyle="dotbox",
        )
        target_y = ttk.Scrollbar(target_wrap, orient="vertical", command=self.target_list.yview)
        self.target_list.configure(yscrollcommand=target_y.set)
        self.target_list.grid(row=0, column=0, sticky="nsew")
        target_y.grid(row=0, column=1, sticky="ns")
        ttk.Button(right, text="전체선택", command=self._select_all_targets).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6)
        )
        self.byte_value = tk.StringVar()
        self.str_value = tk.StringVar()
        byte_entry = ttk.Entry(right, textvariable=self.byte_value, width=16, font=("Consolas", 10))
        byte_entry.grid(row=3, column=0, sticky="ew", padx=(0, 4), pady=2)
        byte_entry.bind("<Return>", lambda _e: self._add_byte())
        ttk.Button(right, text="Byte Add", width=10, command=self._add_byte).grid(row=3, column=1, pady=2)
        str_entry = ttk.Entry(right, textvariable=self.str_value, width=16, font=("Malgun Gothic", 10))
        str_entry.grid(row=4, column=0, sticky="ew", padx=(0, 4), pady=2)
        str_entry.bind("<Return>", lambda _e: self._add_string())
        ttk.Button(right, text="String Add", width=10, command=self._add_string).grid(row=4, column=1, pady=2)
        ttk.Button(right, text="SEND", style="Send.TButton", command=self._send).grid(
            row=5, column=0, columnspan=2, sticky="sew", pady=(8, 0)
        )

        self.root.bind("<Control-Return>", lambda _e: self._send())

    def run(self):
        self.root.mainloop()

    def _on_mode(self, _event=None):
        current = self.ip.get().strip()
        if self.mode.get() == "SERVER":
            if current in ("", "127.0.0.1"):
                self.ip.set("0.0.0.0")
            self.bind_btn.configure(text="BIND")
        else:
            if current in ("", "0.0.0.0"):
                self.ip.set("127.0.0.1")
            self.bind_btn.configure(text="CONNECT")

    def _on_delim(self, _event=None):
        custom = self.delim_name.get() == "직접입력"
        self.custom_entry.configure(state="normal" if custom else "disabled")
        if self.delim_name.get() == "STX/ETX":
            self.string_hint.set("본문만 입력합니다. 앞에 STX(0x02), 뒤에 ETX(0x03)가 붙습니다.  Ctrl+Enter 송신")
        else:
            self.string_hint.set("본문만 입력합니다. 송신 시 구분자가 자동으로 붙습니다.  Ctrl+Enter 송신")
        self._push_framing()

    def _encoding(self):
        return CHARSETS.get(self.charset.get(), "utf-8")

    def _delimiter(self):
        return resolve_delimiter(self.delim_name.get(), self.custom.get(), self._encoding())

    def _push_framing(self):
        try:
            prefix, suffix = self._delimiter()
        except Exception as exc:
            self._log(f"exceptionCaught:구분자 {exc}")
            return
        self.engine.set_framing(prefix, suffix, self._encoding())
        self._push_reply()

    def _push_reply(self):
        if not hasattr(self, "reply_on"):
            return
        self.engine.set_reply(self.reply_on.get(), self.reply_text.get(), self.auto.get())

    def _toggle(self):
        if self.connected:
            self.engine.stop()
            return
        host = self.ip.get().strip()
        port_text = self.port.get().strip()
        try:
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self._log("exceptionCaught:포트는 1~65535 입니다")
            return
        if not host:
            self._log("exceptionCaught:IP를 입력하세요")
            return
        self._push_framing()
        self._save_config()
        try:
            if self.mode.get() == "SERVER":
                self.session = self.engine.start_server(host, port)
            else:
                self.session = self.engine.start_client(host, port)
                self._log(f"connect {host}:{port}")
        except OSError as exc:
            self._log(f"exceptionCaught:{exc}")
            self.status.set("대기")
            return
        self.connected = True
        self._set_conn_controls(False)
        self.bind_btn.configure(text="CLOSE")

    def _set_conn_controls(self, enabled):
        state = "readonly" if enabled else "disabled"
        entry = "normal" if enabled else "disabled"
        self.mode_box.configure(state=state)
        self.ip_entry.configure(state=entry)
        self.port_entry.configure(state=entry)

    def _clean(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _log(self, line):
        line = line.replace("\x00", "")
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        end_line = int(float(self.log.index("end-1c")))
        if end_line > MAX_LOG_LINES:
            self.log.delete("1.0", f"{end_line - 3000}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                self._on_event(event, payload)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(50, self._poll)

    def _on_event(self, event, payload):
        if event == "log":
            self._log(payload)
        elif event == "status":
            self.status.set(payload)
        elif event == "peers":
            self._set_peers(payload)
        elif event == "closed":
            if payload != self.session:
                return
            self.connected = False
            self.session = None
            self._set_conn_controls(True)
            self._on_mode()
            if self.status.get() != "대기" and not str(self.status.get()).startswith("SERVER"):
                self.status.set("대기")

    def _set_peers(self, labels):
        labels = list(labels)
        previous = list(self.target_list.get(0, "end"))
        selected = set(self._selected_targets())
        select_new = (not previous) or set(previous).issubset(selected)
        self.target_list.delete(0, "end")
        for index, label in enumerate(labels):
            self.target_list.insert("end", label)
            if label in selected or (select_new and label not in previous):
                self.target_list.selection_set(index)

    def _selected_targets(self):
        return [self.target_list.get(index) for index in self.target_list.curselection()]

    def _select_all_targets(self):
        if self.target_list.size():
            self.target_list.selection_set(0, "end")

    def _insert_message(self, item):
        self.rx_items.append(item)
        self.msg_list.insert("end", item["display"][:80])
        self._trim_messages()
        self.msg_list.see("end")

    def _trim_messages(self):
        while len(self.rx_items) > 300:
            index = next((i for i, item in enumerate(self.rx_items) if not item.get("saved")), None)
            if index is None:
                break
            del self.rx_items[index]
            self.msg_list.delete(index)

    def _selected_index(self):
        selected = self.msg_list.curselection()
        if not selected:
            return None
        return selected[0]

    def _load_selected(self):
        index = self._selected_index()
        if index is None or index >= len(self.rx_items):
            return
        item = self.rx_items[index]
        if item.get("mode") == "BYTE":
            self.byte_text.delete("1.0", "end")
            self.byte_text.insert("1.0", item.get("bytes") or item["text"])
            self.notebook.select(self.byte_tab)
            self._refresh_preview()
        else:
            self.string_text.delete("1.0", "end")
            self.string_text.insert("1.0", item["text"])
            self.notebook.select(self.string_tab)

    def _delete_selected(self):
        index = self._selected_index()
        if index is None:
            return
        saved = self.rx_items[index].get("saved")
        del self.rx_items[index]
        self.msg_list.delete(index)
        if saved:
            self._write_templates()

    def _keep_current(self):
        text = self.string_text.get("1.0", "end-1c")
        if text == "":
            self._log("exceptionCaught:보관할 STRING 내용이 없습니다")
            return
        item = {
            "saved": True,
            "mode": "STRING",
            "text": text,
            "display": "★ " + text.replace("\n", " "),
        }
        self._insert_message(item)
        self._write_templates()

    def _load_templates(self):
        try:
            with open(messages_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for entry in data:
            text = entry.get("text") if isinstance(entry, dict) else None
            if not isinstance(text, str) or text == "":
                continue
            self.rx_items.append({
                "saved": True,
                "mode": "STRING",
                "text": text,
                "display": "★ " + text.replace("\n", " "),
            })
            self.msg_list.insert("end", self.rx_items[-1]["display"][:80])

    def _write_templates(self):
        records = [{"text": item["text"]} for item in self.rx_items if item.get("saved")]
        try:
            with open(messages_path(), "w", encoding="utf-8") as handle:
                json.dump(records, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._log(f"exceptionCaught:전문 저장 실패 {exc}")

    def _tab_name(self):
        return self.notebook.tab(self.notebook.select(), "text")

    def _send(self):
        self._push_framing()
        prefix, suffix = self._delimiter()
        encoding = self._encoding()
        try:
            if self._tab_name() == "BYTE":
                payload = parse_byte_text(self.byte_text.get("1.0", "end"))
                body_text = "".join(
                    ch for ch in decode_text(payload, encoding).replace("\r", "").replace("\n", "")
                    if ch != "\x00"
                )
            else:
                text = self.string_text.get("1.0", "end-1c")
                payload = text.encode(encoding)
                body_text = text.replace("\r", "").replace("\n", "").replace("\x00", "")
        except ValueError as exc:
            self._log(f"exceptionCaught:{exc}")
            return
        except UnicodeEncodeError:
            self._log(f"exceptionCaught:{self.charset.get()} 로 변환할 수 없는 문자가 있습니다")
            return
        framed = apply_framing(payload, prefix, suffix, self.auto.get())
        if not framed:
            self._log("exceptionCaught:보낼 데이터가 없습니다")
            return
        targets = self._selected_targets()
        if not targets:
            self._log("exceptionCaught:보낼 대상을 선택하세요")
            return
        count, error = self.engine.send(targets, framed)
        if count:
            where = f"{count}곳 " if count > 1 else ""
            shown = body_text if payload else "(구분자만)"
            self._log(f"send {where}Byte:{to_decimal(framed)}")
            self._log(f"send {where}String:{shown}")
        if error:
            self._log(f"exceptionCaught:{error}")

    def _refresh_preview(self):
        raw = self.byte_text.get("1.0", "end").strip()
        if not raw:
            self.preview.set("HEX: (비어 있음)")
            return
        try:
            data = parse_byte_text(raw)
        except ValueError as exc:
            self.preview.set(f"형식 오류: {exc}")
            return
        self.preview.set(f"HEX: {to_hex(data)}    ({len(data)} bytes)")

    def _append_bytes(self, extra):
        try:
            current = parse_byte_text(self.byte_text.get("1.0", "end"))
        except ValueError as exc:
            self._log(f"exceptionCaught:BYTE 내용을 확인하세요 ({exc})")
            return
        merged = current + extra
        self.byte_text.delete("1.0", "end")
        if merged:
            self.byte_text.insert("1.0", to_decimal(merged))
        self.notebook.select(self.byte_tab)
        self._refresh_preview()

    def _add_byte(self):
        raw = self.byte_value.get().strip()
        if not raw:
            self._log("exceptionCaught:Byte Add 값을 입력하세요")
            return
        try:
            extra = bytes((_parse_byte_token(raw),))
        except ValueError as exc:
            self._log(f"exceptionCaught:{exc}")
            return
        self._append_bytes(extra)
        self.byte_value.set("")

    def _add_string(self):
        text = self.str_value.get()
        if text == "":
            self._log("exceptionCaught:String Add 값을 입력하세요")
            return
        self.string_text.insert("end", text)
        self.notebook.select(self.string_tab)
        self.str_value.set("")

    def _load_config(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        if data.get("mode") in ("SERVER", "CLIENT"):
            self.mode.set(data["mode"])
        if data.get("ip"):
            self.ip.set(data["ip"])
        if data.get("port"):
            self.port.set(str(data["port"]))
        saved_delimiter = data.get("delimiter")
        if saved_delimiter in ("STX (0x02)", "ETX (0x03)"):
            saved_delimiter = "STX/ETX"
        if saved_delimiter in DELIMITER_NAMES:
            self.delim_name.set(saved_delimiter)
        if "custom" in data:
            self.custom.set(data["custom"])
        if "auto" in data:
            self.auto.set(bool(data["auto"]))
        if "reply_on" in data:
            self.reply_on.set(bool(data["reply_on"]))
        if "reply_text" in data:
            self.reply_text.set(data["reply_text"])
        if data.get("charset") in CHARSETS:
            self.charset.set(data["charset"])
        self.bind_btn.configure(text="BIND" if self.mode.get() == "SERVER" else "CONNECT")
        self._on_delim()

    def _save_config(self):
        data = {
            "mode": self.mode.get(),
            "ip": self.ip.get().strip(),
            "port": self.port.get().strip(),
            "delimiter": self.delim_name.get(),
            "custom": self.custom.get(),
            "auto": self.auto.get(),
            "charset": self.charset.get(),
            "reply_on": self.reply_on.get(),
            "reply_text": self.reply_text.get(),
        }
        try:
            with open(config_path(), "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._log(f"exceptionCaught:설정 저장 실패 {exc}")

    def _on_close(self):
        self._save_config()
        try:
            self.engine.stop()
        except Exception:
            pass
        self.root.destroy()


def _wait_event(events, kind, predicate, timeout=3):
    import time
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        try:
            event, payload = events.get(timeout=0.1)
        except queue.Empty:
            continue
        seen.append((event, payload))
        if event == kind and predicate(payload):
            return seen
    raise AssertionError(f"{kind} 조건을 찾지 못함. 수신={seen[-8:]}")


def _wait_log(events, needle, timeout=3):
    return _wait_event(events, "log", lambda payload: needle in str(payload), timeout)


def selftest():
    assert apply_framing(b"-", b"", b"\r\n", True) == b"-\r\n"
    assert apply_framing(b"-\r\n", b"", b"\r\n", True) == b"-\r\n"
    assert apply_framing(b"-", b"", b"\r\n", False) == b"-"
    assert apply_framing(b"-", b"\x02", b"\x03", True) == b"\x02-\x03"
    assert apply_framing(b"\x02-\x03", b"\x02", b"\x03", True) == b"\x02-\x03"
    assert apply_framing(b"\x02-", b"\x02", b"\x03", True) == b"\x02-\x03"
    assert apply_framing(b"-\x03", b"\x02", b"\x03", True) == b"\x02-\x03"
    assert parse_byte_text("45 13 10") == bytes((45, 13, 10))
    assert parse_byte_text("2D 0D 0A") == bytes((0x2D, 0x0D, 0x0A))
    assert parse_byte_text("0x2D, 0x0D, 0x0A") == bytes((45, 13, 10))
    assert parse_custom_delimiter(r"\r\n", "utf-8") == b"\r\n"
    assert parse_custom_delimiter("0D 0A", "utf-8") == b"\r\n"
    assert parse_custom_delimiter("0D0A", "utf-8") == b"\r\n"
    assert resolve_delimiter("LINE (CR LF)", "", "utf-8") == (b"", b"\r\n")
    assert resolve_delimiter("NULL (0x00)", "", "utf-8") == (b"", b"\x00")
    assert resolve_delimiter("STX/ETX", "", "utf-8") == (b"\x02", b"\x03")
    buf = bytearray(b"-\r\nAB\r\nC")
    frames = take_frames(buf, b"", b"\r\n")
    assert frames == [(b"-\r\n", True), (b"AB\r\n", True)]
    assert bytes(buf) == b"C"
    assert frame_body(b"-\r\n", b"", b"\r\n", True) == b"-"
    stx_buf = bytearray(b"\x00\x02-\x03\x02OK\x03tail")
    stx_frames = take_frames(stx_buf, b"\x02", b"\x03")
    assert stx_frames == [(b"\x00", False), (b"\x02-\x03", True), (b"\x02OK\x03", True)]
    assert bytes(stx_buf) == b"tail"
    assert frame_body(b"\x02-\x03", b"\x02", b"\x03", True) == b"-"
    raw_events = queue.Queue()
    raw = Engine(raw_events)
    raw.mode = "CLIENT"
    raw.set_framing(b"", b"\x00", "utf-8")
    raw._on_bytes(Peer(None, "peer"), b"ABC")
    _wait_log(raw_events, "Byte:65 66 67")
    _wait_log(raw_events, "String:ABC")
    raw._on_bytes(Peer(None, "peer"), b"Z\x00")
    _wait_log(raw_events, "Byte:90 0")
    _wait_log(raw_events, "String:Z")

    server_events = queue.Queue()
    client_events = queue.Queue()
    server = Engine(server_events)
    client = Engine(client_events)
    server.set_framing(b"", b"\r\n", "utf-8")
    client.set_framing(b"", b"\r\n", "utf-8")
    port = None
    gen = server.start_server("127.0.0.1", 0)
    with server._lock:
        port = server._server.getsockname()[1]
    client.start_client("127.0.0.1", port)
    _wait_event(server_events, "peers", lambda labels: len(labels) > 0)
    _wait_log(client_events, "channelActive")
    framed = apply_framing("-".encode("utf-8"), b"", b"\r\n", True)
    count, error = client.send("ALL", framed)
    assert count == 1 and error == ""
    assert framed == bytes((45, 13, 10))
    _wait_log(server_events, "Byte:45 13 10")
    _wait_log(server_events, "String:-")
    reply = apply_framing("OK".encode("utf-8"), b"", b"\r\n", True)
    count, error = server.send("ALL", reply)
    assert count == 1 and error == ""
    _wait_log(client_events, "String:OK")
    client.stop()
    server.stop()
    assert gen > 0

    app = App()
    try:
        app.reply_on.set(True)
        app.reply_text.set("")
        app.engine.set_framing(b"", b"\x00", "utf-8")
        app.engine.start_server("127.0.0.1", 0)
        with app.engine._lock:
            reply_port = app.engine._server.getsockname()[1]
        sock = socket.create_connection(("127.0.0.1", reply_port), timeout=2)
        sock.settimeout(0.2)
        deadline = time.time() + 2
        while time.time() < deadline and not app.engine._peers:
            app.root.update()
            time.sleep(0.02)
        sock.sendall(b"ABC\x00")
        echoed = b""
        deadline = time.time() + 2
        while time.time() < deadline and echoed != b"ABC\x00":
            app.root.update()
            try:
                echoed += sock.recv(64)
            except socket.timeout:
                pass
        assert echoed == b"ABC\x00", echoed
        app.root.update()
        assert "send" in app.log.get("1.0", "end")
        app.reply_text.set("OK")
        app.auto.set(True)
        app.delim_name.set("NULL (0x00)")
        app._push_framing()
        sock.sendall(b"XYZ")
        custom = b""
        deadline = time.time() + 2
        while time.time() < deadline and custom != b"OK\x00":
            app.root.update()
            try:
                custom += sock.recv(64)
            except socket.timeout:
                pass
        assert custom == b"OK\x00", custom
        sock.close()
    finally:
        app.engine.stop()
        app.root.destroy()
    print("SELFTEST OK")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("teia.tcp.socket.tool")
    except Exception:
        pass
    App().run()


if __name__ == "__main__":
    main()
