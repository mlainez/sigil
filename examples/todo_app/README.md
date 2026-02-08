# AISL Todo Application

Complete web-based TODO application with SQLite database backend, built in pure AISL.

## Quick Start

```bash
# Compile
./compiler/c/bin/aislc examples/todo_app/todo_app.aisl /tmp/todo.aislc

# Run
./compiler/c/bin/aisl-run /tmp/todo.aislc

# Open browser
http://localhost:8080
```

## Features

- Full HTML/CSS/JavaScript UI with Tailwind CSS
- SQLite database backend
- Add, toggle, and delete todos
- Data persists across server restarts
- Modern, responsive interface
- 183 lines of pure AISL code

## Known Limitations

- VM currently crashes when SQLite query returns empty result set
- Workaround: App seeds one welcome task on startup (you can delete it after adding your own tasks)
- Database persists todos between restarts, welcome message only added if not present

## Implementation

The application consists of:
- SQLite database with `todos` table
- TCP server on port 8080
- Single-page HTML interface with embedded JavaScript
- RESTful API endpoints for CRUD operations

## API Endpoints

- `GET /` - Returns the web interface
- `POST /api/add?text=...` - Add new todo
- `POST /api/toggle?id=...` - Toggle todo status
- `POST /api/delete?id=...` - Delete todo

## Database Schema

```sql
CREATE TABLE todos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  done INTEGER DEFAULT 0
);
```

## Technical Stack

- Language: AISL
- Database: SQLite (via process handle)
- Server: TCP sockets (via socket handle)
- Frontend: Vanilla JavaScript

## Example Usage

```lisp
(module todo_app
  (import sqlite)
  
  (fn main -> int
    (set db process (call open "todos.db"))
    (call init_db db)
    
    (set server socket (call tcp_listen 8080))
    (loop
      (set client socket (call tcp_accept server))
      (call handle_request db client))
    (ret 0)))
```

This demonstrates AISL's ability to build production-ready web applications with database persistence.
