# Lab 3 DNS application

The three independent Docker build contexts are `US`, `FS`, and `AS`.
US listens on HTTP 8080, FS on HTTP 9090, and AS on UDP 53533.
Each directory contains its Dockerfile and every file needed to build it.

## Run with Docker

From this directory:

```sh
docker compose -p lab3-dns up --build -d
AS_IP=$(docker inspect lab3-dns-as-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
FS_IP=$(docker inspect lab3-dns-fs-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
curl -i -X PUT http://127.0.0.1:9090/register \
  -H 'Content-Type: application/json' \
  -d "{\"hostname\":\"fibonacci.com\",\"ip\":\"$FS_IP\",\"as_ip\":\"$AS_IP\",\"as_port\":\"53533\"}"
curl -i "http://127.0.0.1:8080/fibonacci?hostname=fibonacci.com&fs_port=9090&number=10&as_ip=$AS_IP&as_port=53533"
```

The registration returns HTTP 201. The US request returns HTTP 200 with `55`.
Container IPs are discovered at runtime rather than hard-coded in the servers.

Run the integration checks against these containers:

```sh
python3 verify.py --output verification.txt
```

The checks cover successful registration, exact UDP records, Fibonacci values,
all missing parameters, invalid numbers, malformed messages, and persistence
after restarting AS. The verifier expects the Compose project name `lab3-dns`.

To stop the application while retaining registered records:

```sh
docker compose -p lab3-dns down
```

## Protocol and assumptions

Registration uses the exact newline-delimited payload, including its final newline:

```text
TYPE=A
NAME=fibonacci.com
VALUE=<FS IPv4 address>
TTL=10
```

AS acknowledges successful registration with the same four-field record.
A query contains only `TYPE=A` and `NAME=fibonacci.com`, each on its own line.
The query response contains `TYPE`, `NAME`, `VALUE`, and `TTL` in that order.
Records are written atomically to `/data/records.json`, backed by a Docker volume.
Registering the same name replaces its A record. TTL is the record's cache lifetime;
it does not delete the authoritative registration after ten seconds.

Fibonacci uses `F(0)=0`, `F(1)=1`, and nonnegative integer indices.
Missing/empty parameters and invalid indices return HTTP 400. An unknown name
returns 404; an AS timeout returns 504; other upstream failures return 502.
The UDP protocol is the assignment's simplified text protocol, not DNS wire format.

## Kubernetes extra credit

`deploy_dns.yml` contains all deployments and services plus an AS persistent volume
claim in the `dns-lab3` namespace. The required NodePorts are:

| Server | Container port | NodePort | Protocol |
|---|---:|---:|---|
| AS | 53533 | 30001 | UDP |
| FS | 9090 | 30002 | TCP |
| US | 8080 | 30003 | TCP |

The cluster needs a default StorageClass and access to the three container images.
Build and publish them to the image names in the manifest before cloud deployment:

```sh
docker compose -p lab3-dns build
docker compose -p lab3-dns push
kubectl apply -f deploy_dns.yml
kubectl -n dns-lab3 rollout status deployment/as
kubectl -n dns-lab3 rollout status deployment/fs
kubectl -n dns-lab3 rollout status deployment/us
```

On a cloud cluster, build for its node architecture (for example `linux/amd64`)
or publish multi-platform images. Allow inbound UDP 30001 and TCP 30002/30003
only as required for this lab. The Docker run and integration verification were
completed locally; a cloud Kubernetes run is a separate extra-credit step.

After deployment, obtain the internal service addresses:

```sh
AS_IP=$(kubectl -n dns-lab3 get service as -o jsonpath='{.spec.clusterIP}')
FS_IP=$(kubectl -n dns-lab3 get service fs -o jsonpath='{.spec.clusterIP}')
```

Send PUT `/register` through the FS NodePort 30002 with `ip=$FS_IP`,
`as_ip=$AS_IP`, and `as_port=53533`. Send the five-parameter US request through
NodePort 30003 with `hostname=fibonacci.com`, `fs_port=9090`, `number=10`,
`as_ip=$AS_IP`, and `as_port=53533`. Internal traffic uses the service ports;
external traffic uses the NodePorts.
