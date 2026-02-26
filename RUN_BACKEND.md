# Running the backend (fix for ERR_CONNECTION_REFUSED)

The React frontend expects the Django API at **http://localhost:8000**. If you see `ERR_CONNECTION_REFUSED`, the backend is not running.

**Quick start:** From this directory run:
```bash
python manage.py runserver 8000
```
Then refresh the React app.

## 1. Install dependencies

```bash
cd My-Restro-Server
pip install -r requirements.txt
```

## 2. Run the server

```bash
python manage.py runserver 8000
```

Then open the React app; API requests will go to `http://localhost:8000`.

## 3. If your backend runs on another host/port

In the **frontend** project (`My-Restro-Web`), set:

- `.env`: `VITE_API_BASE=http://YOUR_HOST:YOUR_PORT/api`

Example: `VITE_API_BASE=http://localhost:9000/api` if the backend runs on port 9000.
