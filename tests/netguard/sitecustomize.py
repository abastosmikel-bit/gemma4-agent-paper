# D0b dry-run network guard: log and refuse every non-loopback connection or name lookup (proof of "never touches the
# internet", even where a library would swallow a failed connection).
import os, socket, sys
_LOG = os.environ.get("NET_GUARD_LOG", "/tmp/net_guard.log")
_LOCAL = ("127.", "::1", "localhost", "0.0.0.0")
def _local(host):
    return isinstance(host, (str, bytes)) and str(host if isinstance(host, str) else host.decode()).startswith(_LOCAL)
def _log(what):
    with open(_LOG, "a") as fh:
        fh.write(f"{os.getpid()} {' '.join(sys.argv[:2])} {what}\n")
_connect, _connect_ex, _gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
def connect(self, addr):
    if isinstance(addr, tuple) and not _local(addr[0]):
        _log(f"connect {addr}"); raise OSError(101, "blocked by D0b dry-run network guard")
    return _connect(self, addr)
def connect_ex(self, addr):
    if isinstance(addr, tuple) and not _local(addr[0]):
        _log(f"connect_ex {addr}"); return 101
    return _connect_ex(self, addr)
def getaddrinfo(host, *a, **k):
    if host is not None and not _local(host):
        _log(f"getaddrinfo {host}"); raise socket.gaierror(-3, "blocked by D0b dry-run network guard")
    return _gai(host, *a, **k)
socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
