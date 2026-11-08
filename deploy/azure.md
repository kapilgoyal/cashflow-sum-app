# Azure Container Apps (combined UI + API)

One always-on container serves the Vite UI and FastAPI. This is the only production host (GHCR image build + Azure Container App).

Do **not** invent Azure credentials. Create the resources below in the [Azure portal](https://portal.azure.com), then paste the IDs Azure shows you into GitHub secrets.

## 1. Resource group, registry, Container App

1. **Resource groups** → **Create** → name e.g. `cashflow-rg` → region **East US** (or yours).
2. **Container registries** → **Create**
   - SKU **Basic** (~$5/month)
   - Same resource group
   - After create: **Access keys** → **Admin user** = On (so the app can pull images; GitHub never stores the password)
3. **Container Apps** → **Create**
   - Name e.g. `cashflow-app`
   - Environment: **Create new** → **Consumption** (not Dedicated)
   - First image: quickstart (`mcr.microsoft.com/k8se/quickstart:latest`) is fine; CI / import replaces it
   - **Ingress**: External / accept traffic from anywhere / target port **80** for the placeholder (workflow sets **8000**)
   - CPU **0.5**, memory **1 GiB**
   - Scale: min replicas **1** (always-on), max **2**
4. After the app exists:
   - **Identity** → System assigned = **On**
   - **Containers** / **Environment variables** (as secrets, not committed):
     - `DATABASE_URL` — omit for sqlite default, or set Neon pooled URL
     - `DATABASE_URL_UNPOOLED` — optional
     - `PORT` = `8000`
   - Registry → **Access control (IAM)** → **Add role assignment** → **AcrPull** → the Container App’s system identity (optional if Admin user is On)

## 2. GitHub OIDC (no client secret)

1. **Microsoft Entra ID** → **App registrations** → **New registration**
   - Name e.g. `github-cashflow-sum-app`
   - Accounts in this organizational directory only
2. Overview: copy **Application (client) ID** and **Directory (tenant) ID**
3. **Certificates & secrets** → **Federated credentials** → **Add credential**
   - Scenario: **GitHub Actions deploying Azure resources**
   - Organization: `kapilgoyal`
   - Repository: `cashflow-sum-app`
   - Entity: **Branch**, branch `master`
4. **Subscriptions** → copy **Subscription ID**
5. Resource group → **Access control (IAM)** → **Add role assignment**
   - **Contributor** on the resource group (covers the Container App)
   - **AcrPush** on the container registry (so CI can `docker push`)

## 3. GitHub Actions secrets

Repo → **Settings** → **Secrets and variables** → **Actions**. Create these **six** (exact names):

| Secret | Value from Azure |
| --- | --- |
| `AZURE_CLIENT_ID` | App registration **Application (client) ID** |
| `AZURE_TENANT_ID` | App registration **Directory (tenant) ID** |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |
| `AZURE_ACR_NAME` | Registry **name** only (`cashflowacr`, not `cashflowacr.azurecr.io`) |
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `AZURE_CONTAINER_APP_NAME` | Container App name |

Do **not** put `DATABASE_URL` in GitHub. It lives on the Container App.

Unused legacy secrets (`RAILWAY_TOKEN`, `RAILWAY_SERVICE_ID`, any Vercel tokens) are not referenced by workflows — remove them in the repo settings when convenient.

Fallback if you cannot use OIDC: a service-principal JSON secret named `AZURE_CREDENTIALS` (Microsoft’s older `azure/login` `creds:` path). Prefer OIDC; this workflow uses OIDC only.

## 4. Deploy

### Path A — GHCR then import (current prototype)

1. Push to `master` (or **Actions** → **Azure proto GHCR image** → **Run workflow**).
2. Image: `ghcr.io/kapilgoyal/cashflow-sum-app:proto` (and `:${{sha}}`).
3. On a machine with `az` logged into the subscription:

```bash
az acr import -n cashflowacr -g cashflow-rg \
  --source ghcr.io/kapilgoyal/cashflow-sum-app:proto \
  --image cashflow-sum-app:proto --force

SUFFIX="m$(date +%m%d%H%M)"
az containerapp update -n cashflow-app -g cashflow-rg \
  --image cashflowacr.azurecr.io/cashflow-sum-app:proto \
  --revision-suffix "${SUFFIX}"
```

4. Health: `GET https://<container-app-fqdn>/health`. UI is `/` (same origin as `/api`).

### Friendly URL (custom domain) — no extra Azure “service”

The default hostname looks like `cashflow-app.<random>.eastus.azurecontainerapps.io`. That random segment is from the managed environment; renaming the Container App alone does **not** remove it.

For a clean name (e.g. `cashflow.yourdomain.com`):

1. Own a domain (registrar cost only — GoDaddy/Namecheap/etc.).
2. In Container App → **Custom domains** → add the hostname → create the DNS CNAME (or A/TXT as Azure shows).
3. Use Azure’s **managed certificate** (free on Container Apps) for HTTPS.

You do **not** need Front Door, Application Gateway, or another paid Azure product just for a nicer name. Optional Front Door/CDN is only if you want global edge/WAF later (extra monthly cost).

### Path B — OIDC workflow → ACR

1. Once the six `AZURE_*` secrets exist, push to `master` or **Actions** → **Azure Container App** → **Run workflow**.
2. Workflow builds, pushes to ACR, and updates the Container App.

## Cost (East US list, Consumption, min replicas = 1)

| Piece | Typical monthly |
| --- | --- |
| ACR **Basic** | **~$5** |
| 0.5 vCPU + 1 GiB, mostly idle | **~$10** after the monthly free grant |
| Same size, busy (month-1 CF / pandas) | **~$34** |
| HTTP requests | **$0** under 2M/month free grant |
| **Estimate** | **~$15–40/month** |

Free grant per subscription/month: 180,000 vCPU-seconds, 360,000 GiB-seconds, 2 million requests. Do **not** pick a Dedicated workload profile (management fee on top).

Sources: [Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing), [pricing](https://azure.microsoft.com/pricing/details/container-apps/).
