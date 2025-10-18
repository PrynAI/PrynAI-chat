📄 docs/infra-setup.md

# Infrastructure Setup — Azure + GitHub (MVP‑0)

This guide documents the exact infra we stood up for the **PrynAI-chat** MVP‑0:

- **Azure Container Apps (ACA)**: `ca-chainlit` (UI) and `ca-gateway` (API)
- **Azure Container Registry (ACR)**
- **Azure Key Vault (AKV)** with **Managed Identity** and secret references
- **LangGraph Platform (Cloud)** (remote graph endpoint)
- **CI/CD** with **GitHub Actions** using **OIDC** login and **ACR Tasks** build
- **Custom domain + TLS**: `chat.prynai.com` on `ca-chainlit` with Azure‑managed cert

> References: ACA custom domains & managed certs; secrets & Key Vault refs; ACR build; image pull via managed identity; GitHub Actions OIDC; SSE format. 

---

## 0) Prerequisites

- Azure CLI installed & logged in (`az version`, `az login`), with access to your subscription.
- Resource Group (RG) created; ACA Environment provisioned.
- ACR and Key Vault created (or use existing).
- GitHub repo with admin access.

Helpful docs: **ACR build** via `az acr build` (builds in Azure, pushes to your registry); **Managed identity image pulls**; **GitHub OIDC login**. 

---

## 1) Shared variables (edit to your values)

```powershell
$SUB="<subId>"
$RG="rg-chat-prynai"
$LOC="eastus"
$ENV_NAME="wittysea-0d591fbf"     # ACA environment name
$ACR_NAME="prynaiacrbe7be4"
$REGISTRY="$ACR_NAME.azurecr.io"

# Apps
$APP_UI="ca-chainlit"
$APP_API="ca-gateway"

# Key Vault
$KV="kv-chat-prynai-eastus"
$KV_URL="https://$KV.vault.azure.net"

# LangGraph
$LG_URL="https://<your-langgraph-deployment>"
$GRAPH="chat"

# Custom domain for UI
$DOMAIN="chat.prynai.com"

```

## 2) Container images (build in ACR)

- We offload Docker builds to Azure with az acr build:

```
# Gateway
az acr build -r $ACR_NAME -t $REGISTRY/prynai/gateway:$(git rev-parse --short HEAD) apps/gateway-fastapi

# Chainlit UI
az acr build -r $ACR_NAME -t $REGISTRY/prynai/chainlit:$(git rev-parse --short HEAD) apps/chainlit-ui

```

## 3) Managed identity & ACR pulls

- Ensure both apps have a system‑assigned identity and can pull from ACR:

```
# Enable system identity
az containerapp identity assign -g $RG -n $APP_API --system-assigned
az containerapp identity assign -g $RG -n $APP_UI  --system-assigned

# Grant AcrPull on ACR to each app identity (principalId)
$GW_MI = az containerapp identity show -g $RG -n $APP_API --query principalId -o tsv
$UI_MI = az containerapp identity show -g $RG -n $APP_UI  --query principalId -o tsv
$ACR_ID = az acr show -n $ACR_NAME -g $RG --query id -o tsv

az role assignment create --assignee-object-id $GW_MI --assignee-principal-type ServicePrincipal --role "AcrPull" --scope $ACR_ID
az role assignment create --assignee-object-id $UI_MI --assignee-principal-type ServicePrincipal --role "AcrPull" --scope $ACR_ID

# Tell each app to use its identity to authenticate to the registry (no username/password)
az containerapp registry set -g $RG -n $APP_API --server $REGISTRY --identity system
az containerapp registry set -g $RG -n $APP_UI  --server $REGISTRY --identity system

```

### Managed identity pulls for ACA, ACR auth with managed identity.


## 4) Key Vault → Container Apps: secret references

- Grant Key Vault Secrets User to each app’s identity at the vault scope:

```
$KV_ID = az keyvault show -g $RG -n $KV --query id -o tsv

az role assignment create --assignee-object-id $GW_MI --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $KV_ID
az role assignment create --assignee-object-id $UI_MI --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $KV_ID

```
- Create secret references on the app that point to Key Vault secrets using:
- keyvaultref:<KV secret URL>,identityref:system:

```
# Gateway secret refs
az containerapp secret set -g $RG -n $APP_API --secrets `
  "openai-api-key=keyvaultref:$KV_URL/secrets/OPENAI-API-KEY,identityref:system" `
  "langsmith-api-key=keyvaultref:$KV_URL/secrets/LANGSMITH-API-KEY,identityref:system" `
  "tavily-api-key=keyvaultref:$KV_URL/secrets/TAVILY-API-KEY,identityref:system"

```

- Bind them as env vars using secretref:<app-secret-name>; also set app config:

```
# Gateway env
az containerapp update -g $RG -n $APP_API --set-env-vars `
  "OPENAI_API_KEY=secretref:openai-api-key" `
  "LANGSMITH_API_KEY=secretref:langsmith-api-key" `
  "TAVILY_API_KEY=secretref:tavily-api-key" `
  "LANGSMITH_ENDPOINT=https://api.smith.langchain.com" `
  "LANGCHAIN_TRACING_V2=true" `
  "LANGGRAPH_URL=$LG_URL" `
  "LANGGRAPH_GRAPH=$GRAPH" `
  "MODERATION_ENABLED=true" `
  "MODERATION_MODEL=omni-moderation-latest"

# Chainlit env
az containerapp update -g $RG -n $APP_UI --set-env-vars `
  "GATEWAY_URL=https://<gateway-fqdn>"

```
## 5) Roll apps to built images


```
# Use the SHAs you built earlier
$GATEWAY_IMAGE="$REGISTRY/prynai/gateway:$(git rev-parse --short HEAD)"
$CHAINLIT_IMAGE="$REGISTRY/prynai/chainlit:$(git rev-parse --short HEAD)"

az containerapp update -g $RG -n $APP_API --image $GATEWAY_IMAGE
az containerapp update -g $RG -n $APP_UI  --image $CHAINLIT_IMAGE

```

- ACA creates a new revision each update.

## 6) CI/CD (GitHub Actions with OIDC)

### Secrets (Repo → Settings → Secrets → Actions):

- AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID (the federated SP)

- Azure Login with OIDC.

### Variables (Repo → Settings → Variables → Actions):

- AZ_RG=rg-chat-prynai, ACR_NAME=<acr>, GATEWAY_APP_NAME=ca-gateway, CHAINLIT_APP_NAME=ca-chainlit

### Workflows:

- Gateway: build in ACR (az acr build) → az containerapp update --image ...

- Chainlit: same pattern

### Azure Login action; ACA GitHub Actions guidance; optional container‑apps‑deploy‑action.


## 7) Custom domain + managed cert (UI)
```
In GoDaddy (prynai.com DNS):

CNAME: chat → <your ACA app FQDN> (e.g., ca-chainlit....azurecontainerapps.io)

TXT: asuid.chat → <verification code> (from app’s customDomainVerificationId)
```

### Bind the hostname and request the managed certificate:
```
# Useful values
$FQDN = az containerapp show -g $RG -n $APP_UI --query "properties.configuration.ingress.fqdn" -o tsv
$ASUID = az containerapp show -g $RG -n $APP_UI --query "properties.customDomainVerificationId" -o tsv

# Add host and issue managed cert (CNAME validation)
az containerapp hostname add  -g $RG -n $APP_UI --hostname $DOMAIN
az containerapp hostname bind -g $RG -n $APP_UI --hostname $DOMAIN --environment $ENV_NAME --validation-method CNAME
```

### Tip: Managed cert requires the app be publicly reachable for DigiCert validation. Keep the TXT asuid.<sub> record in DNS to prevent takeover and simplify renewals.

## 8) Smoke tests

### Healthz:

- curl -s https://<gateway-fqdn>/healthz


### SSE (Windows):
```
curl.exe -N `
  -H "Accept: text/event-stream" `
  -H "Content-Type: application/json" `
  -X POST "https://<gateway-fqdn>/api/chat/stream" `
  --data "{\"message\":\"hello\"}"
```

- SSE frames are event:/data: lines, separated by a blank line; content must be UTF‑8.

## 9) Troubleshooting 

### Key Vault ForbiddenByRbac when setting secrets on the app:

- Assign Key Vault Secrets User to the app’s identity at the vault scope; wait a few minutes for propagation.

### SecretRef ... not found in env:

- The secret set failed earlier (RBAC/typo). Re-run az containerapp secret set and ensure the secret name matches the KV secret name exactly.

### Revisions stuck “Activating”:

- App crashes on startup (e.g., bad env var access or missing deps). Check container logs and verify env names; for Python apps, ensure all runtime deps are listed in pyproject.toml so images include them. ACA will retry the probe until the container starts.

### Image pull auth:

- Make sure the app identity has AcrPull on the registry and containerapp registry set --identity system is configured.

### Custom domain validation fails:

- Re‑check the CNAME targets the ACA FQDN and the TXT asuid.<subdomain> value. Then re-run hostname bind.


