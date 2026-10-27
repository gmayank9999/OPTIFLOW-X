# Deploying OPTIFLOW-X

OPTIFLOW-X runs untrusted, LLM-written C code. It does that safely by
starting a locked-down Docker container per candidate, so **the host must
run a Docker daemon**. That rules out serverless platforms (Cloud Run,
App Engine, Lambda); use a VM. The recipe below is for Google Cloud
Compute Engine; any Linux VM with Docker works the same way.

What gets deployed (`docker-compose.yml`):

| Service | What | Port |
|---|---|---|
| `app` | FastAPI + dashboard + the CrewAI agents; starts sandbox containers on the host daemon | 8000 (public) |
| `reviewer` | the Google ADK Verification Reviewer, served over A2A | 8790 (internal network only) |
| `sandbox` | build-only: the image every candidate runs in | — |

The app reaches the reviewer at `http://reviewer:8790` over the A2A
protocol, the same way it does locally, just across containers.

## 1. Create the VM (Google Cloud)

You need a GCP project with billing enabled and the `gcloud` CLI logged in
(`gcloud auth login`, `gcloud config set project <PROJECT_ID>`).

```bash
gcloud compute instances create optiflow-x \
  --zone=asia-south1-a \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=60GB \
  --tags=optiflow-web \
  --metadata=repo-url=https://github.com/gmayank9999/OPTIFLOW-X.git \
  --metadata-from-file=startup-script=deploy/vm-startup.sh

gcloud compute firewall-rules create optiflow-web \
  --allow=tcp:8000 --target-tags=optiflow-web \
  --source-ranges=<YOUR_IP>/32        # or 0.0.0.0/0 for a public demo
```

`e2-standard-4` (4 vCPU, 16 GB) is enough; the sandbox pins benchmarks to
one core (`SANDBOX_CPUSET`), so a dedicated-core machine type (e.g.
`c3-standard-4`) gives steadier timings than shared-core types.
Indicative cost: e2-standard-4 in asia-south1 is roughly US$0.15/hour
while running; stop the VM when you're not using it.

The startup script installs Docker and clones the repository to
`/opt/optiflow-x`. The VM clones from GitHub, so **push your commits
first** (`git push origin main`). If the repository is private, either
clone over SSH with a deploy key on the VM, or copy the code up with
`gcloud compute scp --recurse . optiflow-x:/opt/optiflow-x`.

## 2. Configure and start

```bash
gcloud compute ssh optiflow-x --zone=asia-south1-a
cd /opt/optiflow-x
sudo cp .env.example .env && sudo nano .env
#   GEMINI_API_KEY=...            (one key is enough: MODEL_ASSIGNMENT=single-cloud)
#   OPTIFLOW_API_TOKEN=<long random string>   <- required for a public VM
#   SANDBOX_CPUSET=2

sudo docker compose build sandbox
sudo DOCKER_GID=$(stat -c %g /var/run/docker.sock) docker compose up -d --build
sudo docker compose logs -f app          # wait for "Application startup complete"
```

Open `http://<VM_EXTERNAL_IP>:8000`. Reading results needs no token;
starting a run asks for the API token once (stored in your browser).

Check from the command line:

```bash
curl http://<VM_EXTERNAL_IP>:8000/api/health
curl -X POST http://<VM_EXTERNAL_IP>:8000/api/runs \
  -H "Authorization: Bearer $OPTIFLOW_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"program_id": "matmul_naive", "variant": "flags_only", "max_attempts": 1}'
```

## 3. Operate

- **Update:** `git pull && sudo docker compose up -d --build`
- **Results** persist in `/opt/optiflow-x/results` on the VM (mounted
  into the app container).
- **Stability table:** timings depend on the machine, so regenerate it on
  the VM before running experiments there:
  `sudo docker compose exec app python -m optiflow.experiments.stability`.
- **Stop paying:** `gcloud compute instances stop optiflow-x --zone=asia-south1-a`

## Security notes

- The app container mounts the Docker socket, which is root-equivalent on
  the VM. That's why the VM should be dedicated to OPTIFLOW-X. Untrusted
  candidate code still never runs in the app container: each candidate
  runs in its own sandbox container with no network, no capabilities, a
  read-only root filesystem, and memory/PID/time limits.
- Set `OPTIFLOW_API_TOKEN` on any reachable deployment, or anyone could
  start runs on your API key.
- Restrict the firewall rule to your own IP unless you're demoing.
- For HTTPS, put Caddy or an HTTPS load balancer in front of port 8000.
