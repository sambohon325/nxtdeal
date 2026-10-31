# DealerOS

DealerOS is a graph-based dealership operations platform built in Python.

## Features

### Knowledge Graph

- Customers
- Vehicles
- Finance Contracts
- Lenders
- Service Records
- Documents
- Images
- Employees
- Managers
- Teams

### Query Engine

- Search
- Graph View
- Graph Tree
- Question Engine

Examples:

- show finance for john
- show vehicle for john
- show lender for john
- show service records for john

### Dashboards

- Sales Dashboard
- Service Dashboard
- Finance Dashboard
- Executive Dashboard

### API

FastAPI + Swagger

Endpoints:

- GET /search
- GET /entity/{id}
- POST /question
- GET /dashboard/sales
- GET /dashboard/service
- GET /dashboard/finance
- GET /dashboard/executive

## Run

```bash
python -m uvicorn api.app:app --reload --port 8001
`