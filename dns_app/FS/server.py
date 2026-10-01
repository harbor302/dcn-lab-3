"""Register an A record over UDP and serve Fibonacci values over HTTP."""
import ipaddress
import re
import socket
from flask import Flask, Response, request


app = Flask(__name__)


def fibonacci(n):
    # Fast doubling keeps the number of arithmetic steps logarithmic in n.
    a, b = 0, 1
    for bit in bin(n)[2:]:
        c = a * (2 * b - a)
        d = a * a + b * b
        a, b = (c, d) if bit == "0" else (d, c + d)
    return a


@app.put("/register")
def register():
    body = request.get_json(silent=True)
    keys = ("hostname", "ip", "as_ip", "as_port")
    if not isinstance(body, dict) or any(not body.get(k) for k in keys):
        return Response("Missing registration parameters\n", status=400)
    try:
        hostname = body["hostname"]
        if not isinstance(hostname, str) or any(c in hostname for c in "\r\n="):
            raise ValueError("Invalid hostname")
        ip = str(ipaddress.IPv4Address(body["ip"]))
        as_ip = str(ipaddress.IPv4Address(body["as_ip"]))
        port_text = str(body["as_port"])
        if not re.fullmatch(r"[0-9]+", port_text):
            raise ValueError("Invalid port")
        as_port = int(port_text)
        if not 1 <= as_port <= 65535:
            raise ValueError("Invalid port")
    except (ValueError, TypeError):
        return Response("Invalid registration parameters\n", status=400)
    message = f"TYPE=A\nNAME={hostname}\nVALUE={ip}\nTTL=10\n".encode()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(3)
            client.connect((as_ip, as_port))
            client.send(message)
            reply = client.recv(4096)
        if reply != message:
            return Response("Registration rejected by AS\n", status=502)
    except socket.timeout:
        return Response("AS registration timed out\n", status=504)
    except OSError:
        return Response("AS registration failed\n", status=502)
    return Response("Registered\n", status=201, mimetype="text/plain")


@app.get("/fibonacci")
def get_fibonacci():
    value = request.args.get("number", "")
    if not re.fullmatch(r"[+]?[0-9]+", value):
        return Response("number must be a nonnegative integer\n", status=400)
    try:
        result = str(fibonacci(int(value)))
    except ValueError:
        return Response("number exceeds the supported integer size\n", status=400)
    return Response(result + "\n", status=200, mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
