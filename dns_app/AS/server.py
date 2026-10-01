"""Persistent authoritative server for the lab's text-based UDP protocol."""
import ipaddress
import json
import os
from pathlib import Path
import socket


DATA_FILE = Path(os.getenv("DATA_FILE", "/data/records.json"))


def parse_message(data):
    fields = {}
    for line in data.decode("utf-8").splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        if key in fields or not value:
            raise ValueError("Invalid or duplicate field")
        fields[key] = value
    if fields.get("TYPE") != "A" or not fields.get("NAME"):
        raise ValueError("Expected TYPE=A and NAME")
    return fields


def format_record(name, record):
    return (f"TYPE=A\nNAME={name}\nVALUE={record['ip']}\n"
            f"TTL={record['ttl']}\n").encode("utf-8")


def handle_message(data, records):
    fields = parse_message(data)
    name = fields["NAME"]
    if set(fields) == {"TYPE", "NAME", "VALUE", "TTL"}:
        ip = str(ipaddress.IPv4Address(fields["VALUE"]))
        ttl = int(fields["TTL"])
        if ttl < 0:
            raise ValueError("TTL must be nonnegative")
        updated = dict(records)
        updated[name] = {"ip": ip, "ttl": ttl}
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = DATA_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(updated, indent=2) + "\n")
        temporary.replace(DATA_FILE)
        records.clear()
        records.update(updated)
        return format_record(name, records[name])
    if set(fields) == {"TYPE", "NAME"}:
        if name not in records:
            return b"ERROR=NOT_FOUND\n"
        return format_record(name, records[name])
    raise ValueError("Unexpected fields")


def main():
    records = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("0.0.0.0", 53533))
        print("AS listening on UDP 53533", flush=True)
        while True:
            data, client = server.recvfrom(4096)
            try:
                reply = handle_message(data, records)
            except (ValueError, UnicodeError):
                reply = b"ERROR=BAD_REQUEST\n"
            except OSError:
                reply = b"ERROR=STORAGE_FAILURE\n"
            server.sendto(reply, client)


if __name__ == "__main__":
    main()
