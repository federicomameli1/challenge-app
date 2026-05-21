> [!WARNING]
> This guide requires access to CrownLabs resources. Contact [stefano.galantino@polito.it](mailto:stefano.galantino@polito.it) and [jacopo.marino@polito.it](mailto:jacopo.marino@polito.it) to replicate the exact setup.

# Verdict + Wayside Monitor — DevOps in Kubernetes

## Overview

This guide describes how to deploy two applications across the CrownLabs infrastructure:

- **Verdict** — the AI-based release readiness console. It is a management tool and runs as a **single stable deployment** on the management cluster, alongside Argo CD. It does not need its own DEV/TEST/PROD pipeline.
- **Wayside Monitor** — the subject application that Verdict analyzes. It goes through the full **DEV → TEST → PROD** GitOps pipeline, providing the evidence bundles and CI results that Verdict evaluates.

### Architecture at a glance

```
┌─────────────────────────────────────────────────────────┐
│                    mgmt cluster                         │
│   Argo CD          +          Verdict                   │
│   (manages all clusters)      (single pod, namespace    │
│                                verdict, always on)      │
└─────────────────────────────────────────────────────────┘
          │ deploys via GitOps
          ├──────────────────────┬──────────────────────┐
          ▼                      ▼                      ▼
   dev cluster            test cluster           prod cluster
   Wayside Monitor        Wayside Monitor        Wayside Monitor
   (one ns per PR)        (wayside-test)         (wayside-prod)
```

### Should you recreate the VMs?

**No.** The K3s installation, Argo CD setup, SSH keys, and merged kubeconfig are all reusable. The only cleanup needed is removing the old `challenge-app` Argo CD resources. This takes under a minute.

The only reason to recreate VMs is if you have unrecoverable configuration drift — for example if `kubectl get nodes` no longer works on one of the clusters.

---

## Index

- [Infrastructure](#infrastructure)
- [Migrate from challenge-app](#migrate-from-challenge-app)
- [Verdict Deployment](#verdict-deployment)
- [Wayside Monitor CI/CD Pipeline](#wayside-monitor-cicd-pipeline)
- [Test the Full Pipeline](#test-the-full-pipeline)
- [Troubleshooting](#troubleshooting)

---

# Infrastructure

> [!NOTE]
> If your VMs are already provisioned and Argo CD is running on mgmt, skip to [Migrate from challenge-app](#migrate-from-challenge-app) or directly to [Verdict Deployment](#verdict-deployment).

## VM Provisioning

Provision **4 Virtual Machines** on [CrownLabs](https://ng.crownlabs.polito.it):

| VM | Type | Recommended label |
|---|---|---|
| Management | Ubuntu Desktop 22.04 (Persistent) | `mgmt` |
| Development | Ubuntu Server 22.04 (Persistent) | `dev` |
| Testing | Ubuntu Server 22.04 (Persistent) | `test` |
| Production | Ubuntu Server 22.04 (Persistent) | `prod` |

> [!WARNING]
> **DO NOT TURN OFF VMs** — IP addresses change on restart, requiring a full infrastructure rebuild.

> [!NOTE]
> Default credentials on all VMs: username `crownlabs`, password `crownlabs`.

> [!WARNING]
> If you want to connect from your local machine, upload your SSH public key to the CrownLabs dashboard **before** creating the VMs. Use bastion `ssh.ng.crownlabs.polito.it` (not the old `ssh.crownlabs.polito.it`).

To create a VM, open the CrownLabs dashboard, navigate to your workspace, and click **Create**.

---

## Prerequisites for all VMs

Run on **each VM** (mgmt, dev, test, prod):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install curl -y
```

---

## Change hostnames

Run the appropriate command on each VM, then reboot:

```bash
# On mgmt
sudo hostnamectl set-hostname trn01-mgmt01

# On dev
sudo hostnamectl set-hostname trn01-dev01

# On test
sudo hostnamectl set-hostname trn01-test01

# On prod
sudo hostnamectl set-hostname trn01-prod01

sudo reboot
```

---

## Collect VM IPs

After rebooting, run this on **each VM** and record the result:

```bash
ip -4 -o addr show enp1s0 | awk '{print $4}' | cut -d/ -f1
```

| VM | IP |
|---|---|
| `mgmt` | *(your value)* |
| `dev` | *(your value)* |
| `test` | *(your value)* |
| `prod` | *(your value)* |

You will need these IPs throughout the guide.

---

## Management VM Setup

### [OPTIONAL] Re-install Firefox

If the default browser fails to open correctly:

```bash
sudo snap remove firefox
sudo snap remove snapd
sudo apt purge snapd
sudo add-apt-repository ppa:mozillateam/ppa -y
sudo apt update
sudo apt install firefox-esr
```

### Install K3s

```bash
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -
```

Wait a few minutes, then verify that all system pods are running:

```bash
kubectl get pods -A
```

Expected output (wait until all are `Running` or `Completed`):

```
NAMESPACE     NAME                                      READY   STATUS      RESTARTS   AGE
kube-system   coredns-7f496c8d7d-xxxxx                  1/1     Running     0          3m
kube-system   helm-install-traefik-crd-xxxxx            0/1     Completed   0          3m
kube-system   helm-install-traefik-xxxxx                0/1     Completed   1          3m
kube-system   local-path-provisioner-xxxxx              1/1     Running     0          3m
kube-system   metrics-server-xxxxx                      1/1     Running     0          3m
kube-system   svclb-traefik-xxxxx                       2/2     Running     0          2m
kube-system   traefik-xxxxx                             1/1     Running     0          2m
```

### Install Helm

Helm is required to create, package, and publish charts that Argo CD will use to deploy applications.

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

Verify:

```bash
helm version
```

Expected output: `version.BuildInfo{Version:"v3.x.x", ...}`

### Install additional Python dependencies

The kubeconfig fix script requires PyYAML. Install it now:

```bash
sudo apt install python3-yaml -y
```

### Install Argo CD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

Wait until all pods are `Running`. This may take a few minutes — run the command repeatedly until all pods are ready:

```bash
kubectl get pod -n argocd
```

Expected output (all pods must be `1/1 Running`):

```
NAME                                                READY   STATUS    RESTARTS   AGE
argocd-application-controller-0                     1/1     Running   0          2m
argocd-applicationset-controller-xxxxx              1/1     Running   0          2m
argocd-dex-server-xxxxx                             1/1     Running   0          2m
argocd-notifications-controller-xxxxx               1/1     Running   0          2m
argocd-redis-xxxxx                                  1/1     Running   0          2m
argocd-repo-server-xxxxx                            1/1     Running   0          2m
argocd-server-xxxxx                                 1/1     Running   0          2m
```

### Expose the Argo CD UI via NodePort

By default, the Argo CD server is `ClusterIP`. Expose it on port `30443`:

```bash
kubectl patch svc argocd-server -n argocd --type='merge' -p '{
  "spec": {
    "type": "NodePort",
    "ports": [
      {
        "name": "http",
        "port": 80,
        "targetPort": 8080
      },
      {
        "name": "https",
        "port": 443,
        "targetPort": 8080,
        "nodePort": 30443
      }
    ]
  }
}'
```

If successful you will see: `service/argocd-server patched`

Verify:

```bash
kubectl get svc argocd-server -n argocd
```

Expected output:

```
NAME            TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)                      AGE
argocd-server   NodePort   10.43.x.x      <none>        80:3XXXX/TCP,443:30443/TCP   5m
```

### Access the Argo CD UI

Open Firefox on the mgmt VM and navigate to:

```
https://localhost:30443
```

Accept the browser security warning and continue. You should see the Argo CD login page.

Retrieve the auto-generated admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

Log in with:
- **Username:** `admin`
- **Password:** the value retrieved above

> [!NOTE]
> Save the password in the Firefox password manager for convenience.

### Install the Argo CD CLI

```bash
curl -sSL -o argocd-linux-amd64 \
  https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo install -m 555 argocd-linux-amd64 /usr/local/bin/argocd
rm argocd-linux-amd64
```

Log in via CLI (replace `<password>` with the value retrieved above):

```bash
argocd login localhost:30443 --insecure --username admin --password <password>
```

Expected output:

```
'admin:login' logged in successfully
Context 'localhost:30443' updated
```

### [OPTIONAL] kubectl alias and autocompletion

```bash
cd ~
echo "alias k='kubectl'" >> ~/.bashrc
kubectl completion bash >> ~/.bashrc
echo "complete -F __start_kubectl k" >> ~/.bashrc
source ~/.bashrc
```

### [OPTIONAL] Install K9s

K9s provides an interactive terminal UI for managing Kubernetes clusters.

```bash
curl -Lo k9s.tar.gz \
  https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz
tar -xzf k9s.tar.gz
sudo mv k9s /usr/local/bin/
rm k9s.tar.gz LICENSE README.md
```

Verify with `k9s` (exit with `Ctrl+C`).

---

## Dev, Test, and Prod VMs Setup

### Install K3s on each env VM

Run this command on **each of dev, test, and prod**:

```bash
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -
```

Verify on each VM:

```bash
kubectl get nodes
```

### Configure SSH access from mgmt to env VMs

On the **mgmt VM**, generate an SSH key pair:

```bash
ssh-keygen -t ed25519
```

Press Enter to accept the default file location and leave the passphrase empty.

Copy the public key to each env VM (use the IPs you recorded earlier):

```bash
USER=crownlabs
DEV_VM=<ip_dev_vm>
TEST_VM=<ip_test_vm>
PROD_VM=<ip_prod_vm>

ssh-copy-id $USER@$DEV_VM
ssh-copy-id $USER@$TEST_VM
ssh-copy-id $USER@$PROD_VM
```

Enter the password `crownlabs` when prompted. Type `yes` if asked about host authenticity — this appears only on the first connection to each VM.

Verify passwordless access (connect and immediately exit each one):

```bash
ssh $USER@$DEV_VM  "exit"
ssh $USER@$TEST_VM "exit"
ssh $USER@$PROD_VM "exit"
```

No password prompt should appear.

### Merge kubeconfigs on the mgmt VM

Copy kubeconfig files from all env VMs and from the mgmt cluster itself:

```bash
mkdir -p ~/kubeconfigs

scp $USER@$DEV_VM:/etc/rancher/k3s/k3s.yaml  ~/kubeconfigs/dev.yaml
scp $USER@$TEST_VM:/etc/rancher/k3s/k3s.yaml ~/kubeconfigs/test.yaml
scp $USER@$PROD_VM:/etc/rancher/k3s/k3s.yaml ~/kubeconfigs/prod.yaml
cp /etc/rancher/k3s/k3s.yaml ~/kubeconfigs/mgmt.yaml
```

Verify that all four files are present:

```bash
ls ~/kubeconfigs
```

Expected: `dev.yaml  mgmt.yaml  prod.yaml  test.yaml`

Create the fix script. By default, K3s sets the same cluster/user/context name (`default`) in every file and points the API server to `127.0.0.1`. This script renames them and updates the server addresses so they can be merged without conflicts.

```bash
nano ~/fix_kubeconfigs.py
```

Paste the following content, replacing the IP placeholders with your actual VM IPs:

```python
#!/usr/bin/env python3
import os, yaml

KUBECONFIG_DIR = os.path.expanduser("~/kubeconfigs")

# ── EDIT THESE ──────────────────────────────────────
DEV_VM  = "<ip_dev_vm>"
TEST_VM = "<ip_test_vm>"
PROD_VM = "<ip_prod_vm>"
# ────────────────────────────────────────────────────

CONFIGS = [
    ("dev.yaml",  "dev",  "dev-user",  "dev",  DEV_VM),
    ("test.yaml", "test", "test-user", "test", TEST_VM),
    ("prod.yaml", "prod", "prod-user", "prod", PROD_VM),
    ("mgmt.yaml", "mgmt", "mgmt-user", "mgmt", "127.0.0.1"),
]

def update_kubeconfig(path, cluster_new, user_new, context_new, server_ip):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    old_context = cfg["contexts"][0]["name"]
    if server_ip != "127.0.0.1":
        cfg["clusters"][0]["cluster"]["server"] = f"https://{server_ip}:6443"
    cfg["clusters"][0]["name"] = cluster_new
    cfg["users"][0]["name"]    = user_new
    cfg["contexts"][0]["name"] = context_new
    cfg["contexts"][0]["context"]["cluster"] = cluster_new
    cfg["contexts"][0]["context"]["user"]    = user_new
    if cfg.get("current-context") == old_context:
        cfg["current-context"] = context_new
    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

for fname, cluster_new, user_new, context_new, server_ip in CONFIGS:
    path = os.path.join(KUBECONFIG_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing: {path}")
    update_kubeconfig(path, cluster_new, user_new, context_new, server_ip)
    print(f"✓ {fname}")

print("\nAll kubeconfigs updated.")
```

Save and exit (`Ctrl+O` → `Enter` → `Ctrl+X`), then run the script:

```bash
python3 ~/fix_kubeconfigs.py
```

Expected output:

```
✓ dev.yaml
✓ test.yaml
✓ prod.yaml
✓ mgmt.yaml

All kubeconfigs updated.
```

Merge all four files into a single kubeconfig:

```bash
mkdir -p ~/.kube
KUBECONFIG=~/kubeconfigs/mgmt.yaml:~/kubeconfigs/dev.yaml:~/kubeconfigs/test.yaml:~/kubeconfigs/prod.yaml \
  kubectl config view --merge --flatten > ~/.kube/config
```

Configure kubectl to always use this merged file:

```bash
echo 'export KUBECONFIG=$HOME/.kube/config' >> ~/.bashrc
source ~/.bashrc
```

Verify the environment variable is set:

```bash
echo $KUBECONFIG
# Expected: /home/crownlabs/.kube/config
```

Verify all four contexts are available:

```bash
kubectl config get-contexts
```

Expected output:

```
CURRENT   NAME   CLUSTER   AUTHINFO    NAMESPACE
          dev    dev       dev-user
*         mgmt   mgmt      mgmt-user
          prod   prod      prod-user
          test   test      test-user
```

Test connectivity to all clusters:

```bash
kubectl config use-context mgmt && kubectl get nodes
kubectl config use-context dev  && kubectl get nodes
kubectl config use-context test && kubectl get nodes
kubectl config use-context prod && kubectl get nodes
kubectl config use-context mgmt
```

Each command should return one node with status `Ready`.

### [OPTIONAL] Port-forward Argo CD to your local machine

Run on your **local machine** (enter `crownlabs` as password when prompted):

```bash
ssh -L 30443:localhost:30443 \
    -J bastion@ssh.ng.crownlabs.polito.it \
    crownlabs@<mgmt_vm_ip>
```

You can then open `https://localhost:30443` in your local browser.

---

## Register env clusters in Argo CD

Make sure you are on the `mgmt` context and logged in to the Argo CD CLI, then register the three env clusters:

```bash
kubectl config use-context mgmt

argocd cluster add dev  -y
argocd cluster add test -y
argocd cluster add prod -y
```

Verify all clusters are registered:

```bash
argocd cluster list
```

Expected output:

```
SERVER                          NAME    VERSION  STATUS
https://XX.XX.XX.XX:6443        dev     1.34     Successful
https://XX.XX.XX.XX:6443        test    1.34     Successful
https://XX.XX.XX.XX:6443        prod    1.34     Successful
https://kubernetes.default.svc  in-cluster
```

> [!NOTE]
> The status may show `Unknown` if no application has synced yet. This is normal and resolves on the first sync.

You can also verify in the Argo CD UI: **Settings → Clusters**.

---

# Migrate from challenge-app

> [!NOTE]
> Follow this section **only** if you previously deployed `challenge-app` (now renamed Verdict) across dev/test/prod. **Skip to [Verdict Deployment](#verdict-deployment) if starting from scratch.**

Remove the old Argo CD resources. Argo CD will automatically prune all Kubernetes objects it had created in the env clusters (namespaces, deployments, services, etc.).

```bash
kubectl config use-context mgmt

# Remove the dev ApplicationSet — this also deletes all per-PR child Applications
kubectl delete applicationset challenge-dev -n argocd

# Remove the test and prod Applications
kubectl delete application challenge-test -n argocd
kubectl delete application challenge-prod -n argocd
```

Wait about 30–60 seconds for Argo CD to finish pruning, then verify that all old namespaces are gone:

```bash
kubectl config use-context dev  && kubectl get ns
kubectl config use-context test && kubectl get ns
kubectl config use-context prod && kubectl get ns
kubectl config use-context mgmt
```

There should be no `challenge-*` or `pr-*` namespaces remaining. If they are still present, wait a bit longer and repeat the check.

If your existing GitOps repo contains old `environments/` directories from the challenge-app setup, you can delete or repurpose them — the new pipelines create their own structure.

---

# Verdict Deployment

Verdict is deployed **once**, on the **mgmt cluster**, in the `verdict` namespace. It runs alongside Argo CD and is always accessible from the management VM. There is no dev/test/prod pipeline for Verdict itself — it is a management tool. The CI/CD is a simple single-environment delivery: merge to `main` → build → deploy.

## Repositories

Create two GitHub repositories:

| Repo | Purpose |
|---|---|
| `verdict` | Application source (React + FastAPI + Python agents), Dockerfile, Helm chart, GitHub Actions |
| `verdict-gitops` | Argo CD Helm values for the mgmt deployment |

> [!WARNING]
> Do not fork existing repositories. Clone and push to a new repo under your own account to avoid GitHub Actions permission issues.

Make the `verdict` repository **public** so the mgmt cluster can pull container images without credentials. Alternatively, configure image pull secrets.

## GitHub repository permissions

In the **verdict** repository:

1. Go to **Settings → Actions → General**
2. Under **Workflow permissions**, select **Read and write permissions**
3. Click **Save**

Create a fine-grained Personal Access Token (PAT) to allow the CI pipeline to push to `verdict-gitops`:

1. GitHub profile photo → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. Set:
   - **Resource owner**: the account that owns `verdict-gitops`
   - **Expiration**: `31/07/2026`
   - **Repository access**: select **Only select repositories** → choose `verdict-gitops`
   - **Repository permissions → Contents**: Read and write
3. Click **Generate token** and **copy it immediately**
4. In the **verdict** repository, go to **Settings → Secrets and variables → Actions → New repository secret**:
   - **Name**: `GITOPS_TOKEN`
   - **Value**: the token you just copied
5. Click **Save**

Add repository variables (**Settings → Secrets and variables → Actions → Variables → New repository variable**):

| Variable | Example value |
|---|---|
| `GITOPS_REPO` | `your-org/verdict-gitops` |
| `APP_NAME` | `verdict` |

## Create the Helm chart

Argo CD deploys applications using Helm charts. You need to create a chart for Verdict, publish it to GHCR once, and then CI only needs to update the image tag on each deploy.

On the **mgmt VM** (or locally), scaffold a new chart:

```bash
helm create verdict-chart
```

This creates the following structure:

```
verdict-chart/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── ingress.yaml
    ├── serviceaccount.yaml
    └── _helpers.tpl
```

Edit `verdict-chart/Chart.yaml` to set the correct name and version:

```yaml
apiVersion: v2
name: verdict
description: Verdict release readiness console
type: application
version: 0.1.0
appVersion: "0.1.0"
```

Edit `verdict-chart/values.yaml` to set the defaults for your application:

```yaml
replicaCount: 1

image:
  repository: ghcr.io/your-org/verdict
  pullPolicy: IfNotPresent
  tag: "latest"

service:
  type: NodePort
  port: 80
  nodePort: 30080

resources: {}

autoscaling:
  enabled: false

serviceAccount:
  create: false

ingress:
  enabled: false
```

In `verdict-chart/templates/deployment.yaml`, verify the container port matches your application (e.g., 80 for nginx serving the built frontend, or 8001 for FastAPI). The default `helm create` template uses `{{ .Values.service.port }}` which is correct.

> [!NOTE]
> The Helm chart defines the **structure** of the deployment. The `values.yaml` inside the chart contains defaults. The `environments/mgmt/values.yaml` in the GitOps repo **overrides** those defaults on each deploy and is the only file that CI touches.

## Publish the Helm chart to GHCR

Package the chart:

```bash
helm package verdict-chart
```

This creates `verdict-0.1.0.tgz` in the current directory.

Log in to GHCR using a GitHub Personal Access Token with `write:packages` scope (you can use a classic PAT for this one-time operation):

```bash
helm registry login ghcr.io \
  --username <your-github-username> \
  --password <your-github-pat>
```

Push the chart to GHCR under an `charts` namespace:

```bash
helm push verdict-0.1.0.tgz oci://ghcr.io/your-org/charts
```

Expected output:

```
Pushed: ghcr.io/your-org/charts/verdict:0.1.0
Digest: sha256:...
```

### Make the Helm package public on GHCR

GHCR packages are private by default. Argo CD needs to pull the chart without credentials, so make it public:

1. Go to your GitHub profile → **Packages**
2. Find the `charts/verdict` package
3. Click **Package settings** (right sidebar)
4. Scroll to **Danger Zone** → **Change visibility** → **Public**
5. Confirm

> [!NOTE]
> You only need to publish the Helm chart **once**. CI will only update the image tag in the GitOps values file — it will not re-publish the chart on every deploy. Only publish a new chart version if you change the Helm templates.

## Initialize the GitOps repo

Clone `verdict-gitops` and create the initial directory structure:

```bash
git clone https://github.com/your-org/verdict-gitops.git
cd verdict-gitops

mkdir -p environments/mgmt

cat > environments/mgmt/values.yaml << 'EOF'
image:
  repository: ghcr.io/your-org/verdict
  tag: "latest"
  pullPolicy: IfNotPresent

service:
  type: NodePort
  port: 80
  nodePort: 30080

replicaCount: 1
EOF

git add .
git commit -m "chore: init mgmt environment"
git push
```

## GitHub Actions workflow for Verdict

`.github/workflows/deploy.yml` in the **verdict** repository:

```yaml
name: Build and Deploy Verdict

on:
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: |
          # add your test/lint commands here
          echo "Tests passed"

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

      - name: Update image tag in GitOps repo
        env:
          GITOPS_TOKEN: ${{ secrets.GITOPS_TOKEN }}
          GITOPS_REPO: ${{ vars.GITOPS_REPO }}
          SHA: ${{ github.sha }}
        run: |
          git clone https://x-access-token:${GITOPS_TOKEN}@github.com/${GITOPS_REPO}.git gitops
          cd gitops
          sed -i "s|tag:.*|tag: \"${SHA}\"|" environments/mgmt/values.yaml
          git config user.email "ci@verdict"
          git config user.name "Verdict CI"
          git add environments/mgmt/values.yaml
          git commit -m "chore: deploy verdict@${SHA}"
          git push
```

## Create and apply the Argo CD Application for Verdict

On the **mgmt VM**, create the manifest:

```bash
nano manifest-verdict.yaml
```

Paste the following content (replace `your-org` with your GitHub organization or username):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: verdict
  namespace: argocd
spec:
  destination:
    name: in-cluster        # deploys to the mgmt cluster itself
    namespace: verdict
  project: default
  sources:
    - repoURL: ghcr.io/your-org/charts
      targetRevision: 0.1.0
      chart: verdict
      helm:
        valueFiles:
          - $values/environments/mgmt/values.yaml
    - repoURL: https://github.com/your-org/verdict-gitops
      targetRevision: main
      ref: values
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

Apply it:

```bash
kubectl apply -f manifest-verdict.yaml
```

### Verify the Argo CD Application

Check that the Application was created:

```bash
kubectl get application verdict -n argocd
```

Expected output:

```
NAME      SYNC STATUS   HEALTH STATUS
verdict   Synced        Healthy
```

> [!NOTE]
> It may take 1–2 minutes for the first sync to complete. The sync status starts as `OutOfSync` or `Unknown` and becomes `Synced` once Argo CD pulls and applies the chart.

If after 2 minutes the status is still not `Synced`, trigger a manual sync:

```bash
argocd app sync verdict
```

Get detailed status:

```bash
argocd app get verdict
```

Verify the pod is running in the `verdict` namespace:

```bash
kubectl get pods -n verdict
kubectl get svc   -n verdict
```

Note the NodePort from the service output and open `http://<mgmt_vm_ip>:30080` in Firefox on the mgmt VM. You should see the Verdict dashboard.

---

# Wayside Monitor CI/CD Pipeline

Wayside Monitor is the **subject application** — the system being developed and promoted through environments. Verdict analyzes its evidence bundles and CI results to decide whether each promotion gate is safe to cross.

## Pipeline summary

| Trigger | Environment | Cluster | Namespace |
|---|---|---|---|
| Pull Request to `main` | Dev (ephemeral, one per PR) | `dev` | `pr-<pr_number>` |
| Merge to `main` | Test | `test` | `wayside-test` |
| GitHub Release | Production | `prod` | `wayside-prod` |

## Repositories

Create two GitHub repositories:

| Repo | Purpose |
|---|---|
| `wayside-monitor` | Application source, Dockerfile, Helm chart, GitHub Actions workflows |
| `wayside-monitor-gitops` | Argo CD resources and Helm values per environment |

> [!WARNING]
> Do not fork. Clone and push to a new repo under your own account.

Make `wayside-monitor` **public** (or configure image pull secrets on the clusters).

## GitHub repository permissions

In the **wayside-monitor** repository:

1. **Settings → Actions → General → Workflow permissions → Read and write permissions → Save**

Create a fine-grained PAT scoped to `wayside-monitor-gitops` with **Contents: Read & Write** (same steps as for Verdict above), and store it as secret `GITOPS_TOKEN` in **wayside-monitor**.

Add repository variables in **wayside-monitor**:

| Variable | Example value |
|---|---|
| `GITOPS_REPO` | `your-org/wayside-monitor-gitops` |
| `APP_NAME` | `wayside-monitor` |

## Create and publish the Helm chart

Follow the same process as for Verdict. On the **mgmt VM** (or locally):

```bash
helm create wayside-monitor-chart
```

Edit `wayside-monitor-chart/Chart.yaml`:

```yaml
apiVersion: v2
name: wayside-monitor
description: Wayside Monitor application
type: application
version: 0.1.0
appVersion: "0.1.0"
```

Edit `wayside-monitor-chart/values.yaml`:

```yaml
replicaCount: 1

image:
  repository: ghcr.io/your-org/wayside-monitor
  pullPolicy: IfNotPresent
  tag: "latest"

service:
  type: NodePort
  port: 80

resources: {}

autoscaling:
  enabled: false

serviceAccount:
  create: false

ingress:
  enabled: false
```

Package and push:

```bash
helm package wayside-monitor-chart
helm push wayside-monitor-0.1.0.tgz oci://ghcr.io/your-org/charts
```

### Make the Helm package public on GHCR

1. GitHub profile → **Packages** → `charts/wayside-monitor`
2. **Package settings → Change visibility → Public** → Confirm

> [!NOTE]
> If you pushed both Verdict and Wayside Monitor charts to `oci://ghcr.io/your-org/charts`, they appear as two separate packages: `charts/verdict` and `charts/wayside-monitor`. Make **both** public.

## Initialize the GitOps repo

Clone `wayside-monitor-gitops` and create the initial directory structure with placeholder values for test and prod:

```bash
git clone https://github.com/your-org/wayside-monitor-gitops.git
cd wayside-monitor-gitops

mkdir -p environments/test environments/prod

cat > environments/test/values.yaml << 'EOF'
image:
  repository: ghcr.io/your-org/wayside-monitor
  tag: "latest"
  pullPolicy: IfNotPresent

service:
  type: NodePort
  port: 80
EOF

cat > environments/prod/values.yaml << 'EOF'
image:
  repository: ghcr.io/your-org/wayside-monitor
  tag: "latest"
  pullPolicy: IfNotPresent

service:
  type: NodePort
  port: 80
EOF

git add .
git commit -m "chore: init test and prod environments"
git push
```

> [!NOTE]
> Do **not** create `environments/dev/` manually. The PR workflow creates and deletes per-PR directories automatically. The ApplicationSet generator will find them dynamically.

## Argo CD manifests

### Dev cluster — ApplicationSet

On the **mgmt VM**:

```bash
nano manifest-wayside-dev.yaml
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: wayside-dev
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/your-org/wayside-monitor-gitops
        revision: main
        directories:
          - path: environments/dev/pr-*
  template:
    metadata:
      name: wayside-dev-{{path.basename}}
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      destination:
        name: dev
        namespace: "{{path.basename}}"
      sources:
        - repoURL: ghcr.io/your-org/charts
          targetRevision: 0.1.0
          chart: wayside-monitor
          helm:
            valueFiles:
              - $values/{{path}}/values.yaml
        - repoURL: https://github.com/your-org/wayside-monitor-gitops
          targetRevision: main
          ref: values
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

### Test cluster — Application

```bash
nano manifest-wayside-test.yaml
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: wayside-test
  namespace: argocd
spec:
  destination:
    name: test
    namespace: wayside-test
  project: default
  sources:
    - repoURL: ghcr.io/your-org/charts
      targetRevision: 0.1.0
      chart: wayside-monitor
      helm:
        valueFiles:
          - $values/environments/test/values.yaml
    - repoURL: https://github.com/your-org/wayside-monitor-gitops
      targetRevision: main
      ref: values
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### Prod cluster — Application

```bash
nano manifest-wayside-prod.yaml
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: wayside-prod
  namespace: argocd
spec:
  destination:
    name: prod
    namespace: wayside-prod
  project: default
  sources:
    - repoURL: ghcr.io/your-org/charts
      targetRevision: 0.1.0
      chart: wayside-monitor
      helm:
        valueFiles:
          - $values/environments/prod/values.yaml
    - repoURL: https://github.com/your-org/wayside-monitor-gitops
      targetRevision: main
      ref: values
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### Apply all three manifests

```bash
kubectl apply -f manifest-wayside-dev.yaml
kubectl apply -f manifest-wayside-test.yaml
kubectl apply -f manifest-wayside-prod.yaml
```

### Verify the Applications were created

```bash
kubectl get application,applicationset -n argocd
```

Expected output:

```
NAME                               SYNC STATUS   HEALTH STATUS
application.argoproj.io/verdict    Synced        Healthy
application.argoproj.io/wayside-test   OutOfSync   Missing
application.argoproj.io/wayside-prod   OutOfSync   Missing

NAME                                         AGE
applicationset.argoproj.io/wayside-dev       10s
```

> [!NOTE]
> `wayside-test` and `wayside-prod` show `OutOfSync / Missing` at this point — that is expected. They will sync to `Healthy` after the first GitHub Actions run pushes a valid image tag. `wayside-dev` shows no child applications yet because there are no PR directories in the GitOps repo.

If you want to trigger a manual sync:

```bash
argocd app sync wayside-test
argocd app sync wayside-prod
```

---

## GitHub Actions workflows

### PR workflow — deploy to dev

Create `.github/workflows/pr-dev.yml` in the **wayside-monitor** repository:

```yaml
name: PR — Deploy to Dev

on:
  pull_request:
    branches: [main]

jobs:
  ci-and-deploy-dev:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Run lint and tests
        run: |
          # add your lint/test commands here
          echo "Tests passed"

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:pr-${{ github.event.pull_request.number }}
            ghcr.io/${{ github.repository }}:${{ github.sha }}

      - name: Create dev namespace in GitOps repo
        env:
          GITOPS_TOKEN: ${{ secrets.GITOPS_TOKEN }}
          GITOPS_REPO: ${{ vars.GITOPS_REPO }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          SHA: ${{ github.sha }}
        run: |
          git clone https://x-access-token:${GITOPS_TOKEN}@github.com/${GITOPS_REPO}.git gitops
          cd gitops
          mkdir -p environments/dev/pr-${PR_NUMBER}
          cat > environments/dev/pr-${PR_NUMBER}/values.yaml << EOF
          image:
            repository: ghcr.io/${{ github.repository }}
            tag: "${SHA}"
          service:
            type: NodePort
          EOF
          git config user.email "ci@wayside"
          git config user.name "Wayside CI"
          git add environments/dev/pr-${PR_NUMBER}/
          git commit -m "chore: deploy wayside-monitor pr-${PR_NUMBER}@${SHA}"
          git push
```

### PR closed — cleanup dev namespace

Create `.github/workflows/pr-cleanup.yml`:

```yaml
name: PR Closed — Cleanup Dev

on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Remove dev namespace from GitOps repo
        env:
          GITOPS_TOKEN: ${{ secrets.GITOPS_TOKEN }}
          GITOPS_REPO: ${{ vars.GITOPS_REPO }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          git clone https://x-access-token:${GITOPS_TOKEN}@github.com/${GITOPS_REPO}.git gitops
          cd gitops
          rm -rf environments/dev/pr-${PR_NUMBER}
          git config user.email "ci@wayside"
          git config user.name "Wayside CI"
          git add -A
          git commit -m "chore: cleanup pr-${PR_NUMBER} dev namespace" || exit 0
          git push
```

When the PR directory is deleted, Argo CD detects the change and removes the namespace from the dev cluster automatically (via `prune: true` and the `resources-finalizer.argocd.argoproj.io` finalizer).

### Merge-to-main — deploy to test

Create `.github/workflows/deploy-test.yml`:

```yaml
name: Main — Deploy to Test

on:
  push:
    branches: [main]

jobs:
  deploy-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:main
            ghcr.io/${{ github.repository }}:${{ github.sha }}

      - name: Update image tag in GitOps repo — test
        env:
          GITOPS_TOKEN: ${{ secrets.GITOPS_TOKEN }}
          GITOPS_REPO: ${{ vars.GITOPS_REPO }}
          SHA: ${{ github.sha }}
        run: |
          git clone https://x-access-token:${GITOPS_TOKEN}@github.com/${GITOPS_REPO}.git gitops
          cd gitops
          sed -i "s|tag:.*|tag: \"${SHA}\"|" environments/test/values.yaml
          git config user.email "ci@wayside"
          git config user.name "Wayside CI"
          git add environments/test/values.yaml
          git commit -m "chore: promote wayside-monitor to test@${SHA}"
          git push
```

### Release — deploy to prod

Create `.github/workflows/deploy-prod.yml`:

```yaml
name: Release — Deploy to Prod

on:
  release:
    types: [published]

jobs:
  deploy-prod:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Verify release commit is on main
        run: |
          git fetch origin main
          if ! git merge-base --is-ancestor ${{ github.sha }} origin/main; then
            echo "ERROR: Release tag is not reachable from main. Aborting."
            exit 1
          fi

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Docker image (immutable digest)
        id: push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.event.release.tag_name }}

      - name: Update GitOps repo — prod (digest-pinned)
        env:
          GITOPS_TOKEN: ${{ secrets.GITOPS_TOKEN }}
          GITOPS_REPO: ${{ vars.GITOPS_REPO }}
          DIGEST: ${{ steps.push.outputs.digest }}
          TAG: ${{ github.event.release.tag_name }}
        run: |
          git clone https://x-access-token:${GITOPS_TOKEN}@github.com/${GITOPS_REPO}.git gitops
          cd gitops
          sed -i "s|repository:.*|repository: ghcr.io/${{ github.repository }}@${DIGEST}|" \
            environments/prod/values.yaml
          sed -i "s|tag:.*|tag: \"\"|" environments/prod/values.yaml
          git config user.email "ci@wayside"
          git config user.name "Wayside CI"
          git add environments/prod/values.yaml
          git commit -m "chore: release wayside-monitor ${TAG} to prod (${DIGEST})"
          git push
```

> [!NOTE]
> Production deploys by **image digest** (e.g. `image@sha256:...`) rather than a mutable tag. This guarantees that test and prod run the exact same binary artifact and prevents tag drift.

---

# Test the Full Pipeline

## 1 — Verify Verdict is running

```bash
kubectl config use-context mgmt
kubectl get pods -n verdict
kubectl get svc  -n verdict
```

Open `http://<mgmt_vm_ip>:30080` in Firefox on the mgmt VM. You should see the Verdict dashboard with the **Pipeline** tab open.

## 2 — Create a PR on Wayside Monitor (Dev deployment)

On the Wayside Monitor repository:

```bash
git checkout -b feature/my-change
# make a visible change (e.g. update a UI string or button color)
git add .
git commit -m "feat: my change"
git push -u origin feature/my-change
```

Open a Pull Request on GitHub: `feature/my-change → main`.

After the `PR — Deploy to Dev` workflow finishes (check the **Actions** tab on GitHub):

- Argo CD creates a new child Application named `wayside-dev-pr-<number>`
- The application deploys to the `dev` cluster in namespace `pr-<number>`

Verify:

```bash
kubectl config use-context dev
kubectl get pods -n pr-<number>
kubectl get svc  -n pr-<number>
```

Note the NodePort from the service output. Open `http://<dev_vm_ip>:<nodePort>` in the browser.

In **Verdict**, the Release Readiness Agent runs automatically on the new evidence bundle and issues its DEV → TEST verdict.

## 3 — Merge the PR (Test deployment)

On GitHub, click **Merge pull request** on your open PR.

After the `Main — Deploy to Test` workflow finishes, Argo CD detects the updated `environments/test/values.yaml` and deploys to the test cluster:

```bash
kubectl config use-context test
kubectl get pods -n wayside-test
kubectl get svc  -n wayside-test
```

Open `http://<test_vm_ip>:<nodePort>`.

In **Verdict**, the Test Evidence Agent analyzes the test results and issues the TEST → PROD verdict.

The dev namespace `pr-<number>` is automatically removed from the dev cluster by the `PR Closed — Cleanup Dev` workflow.

## 4 — Create a Release (Prod deployment)

On the GitHub **wayside-monitor** repository:

1. Click **Releases** in the right sidebar
2. Click **Draft a new release**
3. Click **Choose a tag** → type a new tag (e.g. `v1.0.0`) → **Create new tag**
4. Set the target branch to `main`
5. Add a title and click **Publish release**

After the `Release — Deploy to Prod` workflow finishes, Argo CD deploys to the prod cluster:

```bash
kubectl config use-context prod
kubectl get pods -n wayside-prod
kubectl get svc  -n wayside-prod
```

Open `http://<prod_vm_ip>:<nodePort>`.

In **Verdict**, if the Test Evidence Agent issued a GO, the **Promote to PROD →** button is enabled. Clicking it opens a confirmation dialog and then approves the pending GitHub Actions deployment for the production environment.

---

# Troubleshooting

## ImagePullBackOff on env clusters

Pods fail to start and `kubectl describe pod <pod-name> -n <namespace>` shows `Failed to pull image`.

**Cause:** The container image or Helm chart on GHCR is private.

**Fix:**

1. Go to your repository on GitHub → **Packages**
2. Select the affected image or chart package
3. **Package settings → Change visibility → Public** → Confirm

Do this for both the Docker image (`your-org/wayside-monitor`) and the Helm chart (`your-org/charts/wayside-monitor`).

## Argo CD Application stuck in OutOfSync or Progressing

```bash
# Get detailed status and events
argocd app get wayside-test

# Force a manual sync
argocd app sync wayside-test --force

# Stream logs from the application controller
argocd app logs wayside-test
```

Common causes:
- Image or Helm chart not yet public on GHCR → fix visibility
- `targetRevision` in the Argo CD manifest does not match the published chart version → verify with `helm show chart oci://ghcr.io/your-org/charts/verdict`
- The GitOps repo is not yet accessible from Argo CD → check the repository is public or add credentials in Argo CD Settings → Repositories

## Argo CD shows Unknown cluster status

Normal before any application has been synced. Resolves automatically on first sync.

## kubeconfig context not switching / KUBECONFIG empty

```bash
echo $KUBECONFIG
```

If the output is empty:

```bash
source ~/.bashrc
```

If the merged config does not exist yet, re-run the merge command:

```bash
KUBECONFIG=~/kubeconfigs/mgmt.yaml:~/kubeconfigs/dev.yaml:~/kubeconfigs/test.yaml:~/kubeconfigs/prod.yaml \
  kubectl config view --merge --flatten > ~/.kube/config
```

## Helm push fails with "already exists"

If you try to push a chart version that already exists in the registry:

```
Error: 409: oci artifact already exists
```

Increment the `version` field in `Chart.yaml` (e.g. `0.1.0` → `0.1.1`), re-package, re-push, and update the `targetRevision` in the Argo CD manifests accordingly.

## PR cleanup workflow fails silently

If the `git commit` in the cleanup workflow has nothing to commit (e.g. the PR directory was already gone), the `|| exit 0` at the end prevents the step from failing. This is intentional. Check the Argo CD UI to confirm the namespace was pruned from the dev cluster.

## PyYAML not found when running fix_kubeconfigs.py

```bash
sudo apt install python3-yaml -y
```

Then re-run:

```bash
python3 ~/fix_kubeconfigs.py
```
