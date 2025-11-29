# Sherlock Monorepo

A full-stack application with Python backend (FastAPI + LangChain) and Next.js frontend.




## Project Structure

```
sherlock/
├── backend/           # Python FastAPI backend
│   ├── main.py        # FastAPI application entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/          # Next.js 14 frontend
│   ├── src/
│   ├── Dockerfile
│   └── ...
├── docker-compose.yml # Docker orchestration
└── .env.example       # Root environment template
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Quick Start with Docker

1. Copy the environment file and configure:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. Start all services:
   ```bash
   docker-compose up --build
   ```

3. Access the applications:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Neo4j Browser: http://localhost:7474

### Local Development

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Tech Stack

### Backend
- FastAPI - High-performance Python web framework
- LangChain - LLM orchestration framework
- Neo4j - Graph database
- Python-dotenv - Environment management

### Frontend
- Next.js 14 - React framework with App Router
- TypeScript - Type-safe JavaScript
- Tailwind CSS - Utility-first CSS framework
