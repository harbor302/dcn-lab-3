"""Exercise the running Docker services and check AS persistence."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="verification.txt")
    args = parser.parse_args()
    rows = []

    def check(label, actual, expected):
        if actual != expected:
            raise AssertionError(f"{label}: {actual!r} != {expected!r}")
        rows.append(f"PASS {label}: {actual}")

    def http(port, path, method="GET", body=None):
        payload = json.dumps(body).encode() if body is not None else None
        req = Request(f"http://127.0.0.1:{port}{path}", data=payload, method=method)
        if payload:
            req.add_header("Content-Type", "application/json")
        try:
            reply = urlopen(req, timeout=8)
        except HTTPError as exc:
            reply = exc
        with reply:
            return reply.status, reply.read().decode().strip()

    def udp(message):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(3)
            client.connect(("127.0.0.1", 53533))
            client.send(message.encode())
            return client.recv(4096).decode()

    as_ip = docker("inspect", "lab3-dns-as-1", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}")
    fs_ip = docker("inspect", "lab3-dns-fs-1", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}")
    registration = {"hostname": "fibonacci.com", "ip": fs_ip, "as_ip": as_ip, "as_port": "53533"}
    check("FS registration", http(9090, "/register", "PUT", registration), (201, "Registered"))
    query = "TYPE=A\nNAME=fibonacci.com\n"
    record = f"TYPE=A\nNAME=fibonacci.com\nVALUE={fs_ip}\nTTL=10\n"
    check("AS exact query response", udp(query), record)
    params = {"hostname": "fibonacci.com", "fs_port": "9090", "number": "10", "as_ip": as_ip, "as_port": "53533"}
    for n, expected in ((0, 0), (1, 1), (2, 1), (10, 55), (20, 6765), (50, 12586269025)):
        check(f"FS F({n})", http(9090, f"/fibonacci?number={n}"), (200, str(expected)))
        params["number"] = str(n)
        check(f"US end-to-end F({n})", http(8080, "/fibonacci?" + urlencode(params)), (200, str(expected)))
    for key in params:
        incomplete = {k: v for k, v in params.items() if k != key}
        check(f"US missing {key}", http(8080, "/fibonacci?" + urlencode(incomplete))[0], 400)
    for value in ("abc", "1.5", "-1", ""):
        check(f"FS invalid number {value!r}", http(9090, "/fibonacci?" + urlencode({"number": value}))[0], 400)
        invalid = dict(params, number=value)
        check(f"US invalid number {value!r}", http(8080, "/fibonacci?" + urlencode(invalid))[0], 400)
    for key in registration:
        incomplete = {k: v for k, v in registration.items() if k != key}
        check(f"FS missing {key}", http(9090, "/register", "PUT", incomplete)[0], 400)
    check("FS invalid JSON object", http(9090, "/register", "PUT", [1, 2])[0], 400)
    check("FS invalid IP", http(9090, "/register", "PUT", dict(registration, ip="not-an-ip"))[0], 400)
    check("AS unknown name", udp("TYPE=A\nNAME=missing.example\n"), "ERROR=NOT_FOUND\n")
    check("AS malformed registration", udp("TYPE=A\nNAME=test\nVALUE=bad\nTTL=10\n"), "ERROR=BAD_REQUEST\n")
    check("AS duplicate fields", udp("TYPE=A\nNAME=test\nNAME=other\n"), "ERROR=BAD_REQUEST\n")
    check("AS remains responsive", udp(query), record)
    invalid = dict(params, hostname="missing.example")
    check("US unknown hostname", http(8080, "/fibonacci?" + urlencode(invalid))[0], 404)
    check("US invalid port", http(8080, "/fibonacci?" + urlencode(dict(params, fs_port="1.5")))[0], 400)
    docker("restart", "lab3-dns-as-1")
    for attempt in range(5):
        try:
            persisted = udp(query)
            break
        except (OSError, socket.timeout):
            if attempt == 4:
                raise
            time.sleep(0.2)
    check("AS record survives container restart", persisted, record)
    check("AS stored file", json.loads(docker("exec", "lab3-dns-as-1", "cat", "/data/records.json")), {"fibonacci.com": {"ip": fs_ip, "ttl": 10}})
    params["number"] = "10"
    check("US after AS restart", http(8080, "/fibonacci?" + urlencode(params)), (200, "55"))
    rows.insert(0, f"Docker AS={as_ip}:53533/udp, FS={fs_ip}:9090, US=127.0.0.1:8080")
    rows.append(f"{len(rows)-1} checks passed.")
    Path(args.output).write_text("\n".join(rows) + "\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
