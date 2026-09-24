# SDA-Chatbot Project

By Yazeed Komosany

An Azure-hosted chatbot with standard chat, PDF upload, retrieval-augmented generation, persistent chat history, and automated Docker deployment.

## Architecture

- Streamlit frontend
- FastAPI backend
- OpenRouter chat and embedding models
- ChromaDB vector storage
- Azure Database for PostgreSQL
- Azure Blob Storage
- Azure Key Vault
- Azure VM with Docker Compose
- GitHub Actions and Docker Hub CI/CD

## Local Configuration

Create `.env` from `.env.example` and provide the required local values. Never commit `.env`, `terraform.tfvars`, Terraform state, API keys, passwords, or SAS tokens.

## Terraform

```powershell
terraform init
terraform plan -out=tfplan
terraform apply "tfplan"
terraform output
```

## Application Deployment

Every push to `main` runs GitHub Actions to:

1. Validate Python, Terraform, and Docker Compose.
2. Build the backend and chatbot images.
3. Push commit-SHA and `latest` tags to Docker Hub.
4. Authenticate to Azure using OIDC.
5. Deploy the exact commit-SHA images to the VM.
6. Run backend and frontend health checks.

## Cost Control

Stop compute when the project is not in use:

```powershell
az vm deallocate --resource-group openrouter-stage5-rg --name openrouter-vm
az postgres flexible-server stop --resource-group openrouter-stage5-rg --name openrouter-pg-server-8lqjqk
```

Start PostgreSQL before starting the VM:

```powershell
az postgres flexible-server start --resource-group openrouter-stage5-rg --name openrouter-pg-server-8lqjqk
az vm start --resource-group openrouter-stage5-rg --name openrouter-vm
```

## Rebuild After `terraform destroy`

### Before Destroy

Back up:

- PostgreSQL
- Blob Storage
- ChromaDB volume
- Key Vault secrets
- Terraform outputs

Keep locally:

- `.env`
- `terraform.tfvars`
- SSH public key

### Recreate Infrastructure

```powershell
terraform init
terraform plan -out=tfplan
terraform apply "tfplan"
terraform output
```

Save the new:

- Public IP
- PostgreSQL hostname
- Key Vault name
- Managed identity client ID
- Storage account name

### Recreate Key Vault Secrets

```text
PROJ-DB-NAME=appdb
PROJ-DB-USER=azureadmin
PROJ-DB-PASSWORD=<terraform.tfvars password>
PROJ-DB-HOST=<new PostgreSQL hostname>
PROJ-DB-PORT=5432
PROJ-OPENAI-API-KEY=<OpenRouter key>
PROJ-AZURE-STORAGE-SAS-URL=<new SAS URL>
PROJ-AZURE-STORAGE-CONTAINER=pdf-container
PROJ-CHROMADB-HOST=chromadb
PROJ-CHROMADB-PORT=8000
```

### Restore GitHub Actions Permission

Assign `Virtual Machine Contributor` on the new VM to:

```text
9470596d-1a1b-4e58-8ea5-bbbf7ecad08a
```

### Configure VM

```bash
git clone https://github.com/MaouXsama/Openrouter.git /home/azureuser/Openrouter
cd /home/azureuser/Openrouter
```

Create `.env`:

```env
KEY_VAULT_NAME=<new Key Vault name>
AZURE_CLIENT_ID=<new managed identity client ID>
DOCKERHUB_NAMESPACE=yazeedmk0
IMAGE_TAG=latest
```

Deploy:

```bash
sudo docker compose pull
sudo docker compose up -d --no-build
sudo docker compose ps
```

Open:

```text
http://<new-public-ip>:8501
```

Test normal chat, save/load, PDF upload, and RAG.
