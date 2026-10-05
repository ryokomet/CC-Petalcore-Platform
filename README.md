# Petalcore Platform

This is a combined deployment source for Petalcore Index, Petalcore ID, Petalcore Select, and their shared FastAPI service. It is assembled from copies of the existing repositories; it does not modify those repositories.

## Pages

| App | Page | API access |
| --- | --- | --- |
| Petalcore Index | /index/ | Plant library routes, Index client key |
| Petalcore ID | /id/ | Plant identification route, ID client key |
| Petalcore Select | /select/ | Plant library placeholder, Select client key |

The shared API is available under /api/v1. The root page links to all three apps. Select is still the Index placeholder in the source repositories; this deployment source does not add the recommendation questionnaire or recommendation endpoint.

## API keys

The server reads PETALCORE_INDEX_API_KEY, PETALCORE_ID_API_KEY, and PETALCORE_SELECT_API_KEY separately. The Index and Select keys are accepted on the shared plant-library routes; the ID key is accepted only on /api/v1/identify.

Browser client keys are public identifiers because browser code must send them. They are not private user passwords. PLANTNET_API_KEY is the private provider credential and must only be set in the Vercel environment or a local ignored .env file.

## Local run

From this folder in PowerShell, create an environment and install the packages listed in requirements.txt:

    py -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    Copy-Item .env.example .env

Put the private Pl@ntNet credential in .env, then start FastAPI:

    .\.venv\Scripts\python.exe -m uvicorn api.index:app --reload --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000/ or one of the app paths above. /health reports whether the Pl@ntNet credential is configured.

## Vercel setup

Create a Git repository from this folder and import that repository as one Vercel project with the repository root as the project root. The included vercel.json selects FastAPI. Set these Vercel environment variables:

- PETALCORE_INDEX_API_KEY
- PETALCORE_ID_API_KEY
- PETALCORE_SELECT_API_KEY
- PLANTNET_API_KEY
- PUBLIC_API_BASE_URL=/api/v1
- ALLOWED_ORIGINS=http://127.0.0.1:5500,http://localhost:5500

Keep the three browser client keys aligned with this source's frontends if you change their defaults. Leave ALLOW_LOCAL_DEV unset on Vercel; the listed Live Server origins are allowed explicitly.

The existing Petalcore ID Live Server client is configured to try https://ryokomet-cloudcomputing.vercel.app for the shared API. If this platform is deployed at a different Vercel URL, update SHARED_API_ORIGIN in the original Petalcore ID api/app.js to that URL after the deployment is created. Then refresh the Live Server page. The deployed API must include this platform source before that remote connection can work.

## Deployment notes

The Vercel CLI is not included in this source. Import the Git repository through the Vercel dashboard or install and authenticate the CLI on the development machine. Do not commit .env.
