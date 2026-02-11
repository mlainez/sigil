# Sigil Todo Application

Complete web-based TODO application with SQLite database backend, built in pure Sigil using non-blocking event-driven architecture.

## Files

- `todo_app.sigil` - Sigil backend server (227 lines) - non-blocking event loop
- `index.html` - HTML/CSS/JavaScript frontend template
- `todos.db` - SQLite database (created at runtime)

## Quick Start

```bash
# Run
./interpreter/_build/default/vm.exe examples/todo_app/todo_app.sigil

# Open browser
http://localhost:8080
```

## Features

- **Non-blocking event-driven architecture** - handles multiple concurrent requests
- Full HTML/CSS/JavaScript UI with Tailwind CSS
- SQLite database backend
- Add, toggle, and delete todos
- Data persists across server restarts
- Modern, responsive interface
- Starts with empty database - add your own tasks!
- Clean separation: HTML template in `index.html`, logic in Sigil
- Uses `socket_select` for efficient I/O multiplexing

## Implementation

The application uses a **non-blocking event-driven architecture**:

- SQLite database with `todos` table
- TCP server on port 8080 with `socket_select` multiplexing
- Event loop that monitors server socket and active client connections
- Per-client HTTP request buffering until complete (`\r\n\r\n` marker)
- External HTML template (`index.html`) loaded at runtime
- Dynamic data injection using template replacement
- RESTful API endpoints for CRUD operations

### Event Loop Pattern

The server uses `socket_select` to efficiently handle multiple concurrent clients:

```lisp
(loop
  ; Build array of sockets to monitor (server + all clients)
  (set inputs array (array_new))
  (array_push inputs server)
  ; ... add all client sockets ...
  
  ; Wait for ready sockets (non-blocking)
  (set ready array (socket_select inputs))
  
  ; Handle ready sockets
  ; - Index 0: new client connection (tcp_accept)
  ; - Other indices: client data ready (tcp_receive)
  )
```

This allows the server to:
- Accept new connections while serving existing clients
- Handle multiple concurrent HTTP requests efficiently
- Never block waiting for I/O

### Template System

The HTML template uses a placeholder `__TODOS_DATA__` which is replaced with the actual todo JSON data at runtime:

```javascript
// In index.html
let t=__TODOS_DATA__;

// At runtime, Sigil replaces this with:
let t=[{"id":1,"text":"Buy milk","done":false}];
```

This allows easy customization of the UI without modifying Sigil code.

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

- Language: Sigil
- Database: SQLite (via process handle)
- Server: TCP sockets (via socket handle)
- Frontend: Vanilla JavaScript

## Example Usage

```lisp
(module todo_app
  (import sqlite)
  (import string_utils)
  
  (fn main -> int
    (set db process (open "todos.db"))
    (exec db "CREATE TABLE IF NOT EXISTS todos (...)")
    
    (set server socket (tcp_listen 8080))
    (set clients array (array_new))
    (set buffers array (array_new))
    
    (loop
      ; Monitor server + all clients with socket_select
      (set inputs array (array_new))
      (array_push inputs server)
      ; ... add clients ...
      
      (set ready array (socket_select inputs))
      
      ; Handle new connections and client data
      ; Process complete HTTP requests (ending with \r\n\r\n)
      ))
    (ret 0)))
```

This demonstrates Sigil's ability to build production-ready web applications with:
- Non-blocking I/O and event-driven architecture
- Database persistence
- Concurrent request handling
- Efficient resource utilization
