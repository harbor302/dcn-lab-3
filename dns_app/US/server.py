"""Resolve the FS hostname using AS, then forward the Fibonacci request."""
import ipaddress
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener
from flask import Flask, Response, request


app = Flask(__name__)
opener = build_opener(ProxyHandler({}))


@app.get("/fibonacci")
def get_fibonacci():
    keys = ("hostname", "fs_port", "number", "as_ip", "as_port")
    if any(not request.args.get(k) for k in keys):
        return Response("Missing request parameters\n", status=400)
    hostname = request.args["hostname"]
    number = request.args["number"]
    try:
        if any(c in hostname for c in "\r\n="):
            raise ValueError("Invalid hostname")
        if not re.fullmatch(r"[+]?[0-9]+", number):
            raise ValueError("Invalid number")
        port_values = [request.args["fs_port"], request.args["as_port"]]
        if any(not re.fullmatch(r"[0-9]+", p) for p in port_values):
            raise ValueError("Invalid port")
        fs_port, as_port = map(int, port_values)
        if not all(1 <= p <= 65535 for p in (fs_port, as_port)):
            raise ValueError("Invalid port")
        as_ip = str(ipaddress.IPv4Address(request.args["as_ip"]))
    except ValueError:
        return Response("Invalid request parameters\n", status=400)
    query = f"TYPE=A\nNAME={hostname}\n".encode()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(3)
            client.connect((as_ip, as_port))
            client.send(query)
            reply = client.recv(4096).decode("utf-8")
        if reply == "ERROR=NOT_FOUND\n":
            return Response("Hostname not registered\n", status=404)
        fields = dict(line.split("=", 1) for line in reply.splitlines())
        if set(fields) != {"TYPE", "NAME", "VALUE", "TTL"}:
            raise ValueError("Invalid DNS response")
        if fields["TYPE"] != "A" or fields["NAME"] != hostname or int(fields["TTL"]) < 0:
            raise ValueError("Mismatched DNS response")
        fs_ip = str(ipaddress.IPv4Address(fields["VALUE"]))
    except socket.timeout:
        return Response("AS query timed out\n", status=504)
    except (OSError, ValueError, UnicodeError):
        return Response("AS query failed\n", status=502)
    url = f"http://{fs_ip}:{fs_port}/fibonacci?" + urlencode({"number": number})
    try:
        with opener.open(url, timeout=5) as reply:
            return Response(reply.read(), status=200, mimetype="text/plain")
    except HTTPError as exc:
        return Response(exc.read(), status=exc.code, mimetype="text/plain")
    except (URLError, TimeoutError, OSError):
        return Response("FS request failed\n", status=502)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
