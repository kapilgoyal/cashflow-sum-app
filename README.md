# Sum App

Minimal React + FastAPI hello-world: two numbers in, one sum out.

## Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- `GET /api/sum?a=2&b=3` → `{"sum":5.0}`
- `POST /api/sum` with JSON `{"a":2,"b":3}` → `{"sum":5.0}`

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). The Vite proxy forwards `/api` to the backend on port 8000, so run the backend first.

## Git (optional)

Git is optional for local-only use. You do not need a GitHub account or a remote repo to install dependencies and run this app; `npm install` and `pip install` work from the folder as-is. Init git only if you want local history or version control for yourself.
