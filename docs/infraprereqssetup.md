

## (prereqs) for production : bootstrap setup 

- Github repo can deploy to Azure Container Apps (ACA) using Key Vault for secrets and GitHub Actions (OIDC) for CI/CD

- Resource Group
- Azure Container Registry (ACR)
- Log Analytics workspace
- Container Apps Environment (ACA Env) (apps will be created during MVP‑0)
- Azure Key Vault (RBAC) with  API keys as secrets
- GitHub OIDC trust (App Registration + federated credential) + role assignments so Actions can build/push to ACR and deploy to ACA
- These steps follow Azure’s official quickstarts for Container Apps, ACR, Key Vault + RBAC, and GitHub OIDC. 



0) Prerequisites on your machine

Install Azure CLI and login:

- az login
- az account set --subscription "<YOUR_SUBSCRIPTION_ID>"


Install/upgrade the Container Apps extension:

- az extension add --name containerapp --upgrade


(Optional) Ensure providers are registered:

- az provider register --namespace Microsoft.App
- az provider register --namespace Microsoft.OperationalInsights
- az provider register --namespace Microsoft.ContainerRegistry
- az provider register --namespace Microsoft.KeyVault



1) Set variables (PowerShell)
$RG="rg-chat-prynai"
$LOC="eastus"                     # pick your region
$ACAENV="aca-chat-prynai"
$ACR="prynaiacr$([System.Guid]::NewGuid().ToString('N').Substring(0,6))"  # must be globally unique
$KV="kv-chat-prynai-$($LOC)"
$LA="law-chat-prynai"
$SUB=$(az account show --query id -o tsv)

2) Resource Group, Log Analytics, ACA Environment
# Resource Group
az group create -n $RG -l $LOC

# Log Analytics (required by ACA env)
az monitor log-analytics workspace create -g $RG -n $LA -l $LOC
$LAWID=$(az monitor log-analytics workspace show -g $RG -n $LA --query customerId -o tsv)
$LAWKEY=$(az monitor log-analytics workspace get-shared-keys -g $RG -n $LA --query primarySharedKey -o tsv)

# Container Apps Environment
az containerapp env create -g $RG -n $ACAENV -l $LOC --logs-workspace-id $LAWID --logs-workspace-key $LAWKEY


A Log Analytics workspace is required for Container Apps environments.


3) Azure Container Registry (ACR)
az acr create -g $RG -n $ACR --sku Basic -l $LOC
$ACR_ID=$(az acr show -g $RG -n $ACR --query id -o tsv)
$ACR_LOGIN=$(az acr show -g $RG -n $ACR --query loginServer -o tsv)


We’ll push images here from GitHub Actions. 


4) Key Vault (RBAC) + secrets

Create a vault with RBAC authorization (recommended) and add your secrets. We’ll wire ACA to read them via managed identity during app creation.

# Create Key Vault with RBAC
az keyvault create -g $RG -n $KV -l $LOC --enable-rbac-authorization true

# Add secrets (add what you actually need now; you can add more later)
## Assign the right RBAC role
### Find your user object ID
- az ad signed-in-user show --query id -o tsv
```
az role assignment create `
  --role "Key Vault Administrator" `
  --assignee "970a5cab-4b2f-46bf-865e-ba2fd82fa4ad" `
  --scope $(az keyvault show -g $RG -n $KV --query id -o tsv)
```

# Use your real values instead of '...'
az keyvault secret set --vault-name $KV --name "OPENAI--API--KEY" --value "..."
az keyvault secret set --vault-name $KV --name "TAVILY--API--KEY" --value "..."
az keyvault secret set --vault-name $KV --name "LANGSMITH--API--KEY" --value "..."


With RBAC you grant identities roles like Key Vault Secrets User for read access; we’ll assign these to the Container Apps’ managed identities when we create the apps. 


During MVP‑0 we’ll reference these KV secrets directly from the Container Apps so they’re injected as env vars securely (managed identity → Key Vault). ACA’s doc covers Key Vault secret references. 


5) GitHub Actions OIDC trust (no long‑lived secrets)

This lets the workflow in PrynAI/PrynAI-chat log in to Azure using short‑lived tokens.

5.1 Create an App Registration and Service Principal
$APP_NAME="prynai-githactions-oidc"
$APP_ID=$(az ad app create --display-name $APP_NAME --query appId -o tsv)
# Ensure a Service Principal exists (needed for role assignments)
az ad sp create --id $APP_ID | Out-Null

5.2 Add a Federated Credential for your repo’s main branch
$FC = '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:PrynAI/PrynAI-chat:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

az ad app federated-credential create `
  --id $APP_ID `
  --parameters federated-cred.json



This is the official pattern for Azure Login with OIDC. 


5.3 Role assignments for CI/CD

Give the SP enough rights to push to ACR and deploy to ACA in your RG.

# Scope = resource group (you can scope narrower later)
$SCOPE="/subscriptions/$SUB/resourceGroups/$RG"

# Contributor for ACA deploys (or use Container Apps specific roles)
az role assignment create --assignee $APP_ID --role "Contributor" --scope $SCOPE

# ACR push rights (scope at the registry resource)
az role assignment create --assignee $APP_ID --role "AcrPush" --scope $ACR_ID


Azure’s Container Apps + GitHub Actions guide calls out this flow. 


5.4 Add GitHub repo secrets/vars for workflows

In GitHub → Settings → Secrets and variables → Actions:

Secrets

AZ_TENANT_ID = az account show --query tenantId -o tsv

AZ_SUBSCRIPTION_ID = $SUB

AZ_FEDERATED_CLIENT_ID = $APP_ID (the App Registration’s Application (client) ID)

Variables (example names match your workflow YAML)

AZ_RG = $RG

ACR_NAME = $ACR

ACA_ENV = $ACAENV

GATEWAY_APP_NAME = prynai-gateway

CHAINLIT_APP_NAME = prynai-chainlit

Your existing GitHub workflows will use azure/login@v2 and azure/container-apps-deploy-action@v2; these are the official actions. 



# Confirm resources
az group show -n $RG --query "{name:name,location:location}"
az acr show -n $ACR --query "{loginServer:loginServer,sku:sku.name}"
az containerapp env show -g $RG -n $ACAENV --query "{name:name,location:location}"
az keyvault show -g $RG -n $KV --query "{name:name,propertiesRBAC:properties.enableRbacAuthorization}"
az keyvault secret list --vault-name $KV --query "[].name"


### We now have:

- RG + ACR + Log Analytics + ACA Env 

- Key Vault (RBAC) with initial secrets 

- GitHub OIDC trust + role assignments 