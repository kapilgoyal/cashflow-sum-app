# Azure Container Apps (combined UI + API)

One always-on container serves the Vite UI and FastAPI. Vercel and Railway stay up until you cut over.

Do **not** invent Azure credentials. Create the resources below in the [Azure portal](https://portal.azure.com), then paste the IDs Azure shows you into GitHub secrets.

## 1. Resource group, registry, Container App

1. **Resource groups** → **Create** → name e.g. `cashflow` → region **East US** (or yours).
2. **Container registries** → **Create**
   - SKU **Basic** (~$5/month)
   - Same resource group
   - After create: **Access keys** → **Admin user** = On (so the app can pull images; GitHub never stores the password)
3. **Container Apps** → **Create**
   - Name e.g. `cashflow-sum-app`
   - Environment: **Create new** → **Consumption** (not Dedicated)
   - First image: quickstart (`mcr.microsoft.com/k8se/quickstart:latest`) is fine; GitHub replaces it
   - **Ingress**: External / accept traffic from anywhere / target port **80** for the placeholder (workflow sets **8000**)
   - CPU **0.5**, memory **1 GiB**
   - Scale: min replicas **1** (always-on), max **2**
4. After the app exists:
   - **Identity** → System assigned = **On**
   - **Containers** / **Environment variables** (as secrets, not committed):
     - `DATABASE_URL` — same Neon pooled URL as Railway
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

Fallback if you cannot use OIDC: a service-principal JSON secret named `AZURE_CREDENTIALS` (Microsoft’s older `azure/login` `creds:` path). Prefer OIDC; this workflow uses OIDC only.

## 4. Deploy

1. Merge this PR (or run **Actions** → **Azure Container App** → **Run workflow** on `master`).
2. Open the Container App URL Azure prints. Health: `GET /health`. UI is `/` (same origin as `/api`).
3. Leave Vercel (`VITE_API_BASE_URL` → Railway) until the Azure URL is good, then point DNS / users at Azure and stop the other two hosts.

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
