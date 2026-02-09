# AISL Chat App

A real-time chat application built with AISL featuring a modern web interface.

## Files

- `chat_server.aisl` - Chat server that handles multiple clients and broadcasts messages (49 lines)
- `chat_client.aisl` - Web-based chat client with HTTP interface (254 lines)
- `chat.html` - HTML/CSS/JavaScript frontend with Tailwind CSS

## Architecture

### Chat Server (Port 8080)
- Non-blocking event-driven TCP server
- Broadcasts all messages to all connected clients
- Uses `socket_select` for efficient I/O multiplexing

### Chat Client (Configurable HTTP Port)
- Dual-socket event loop:
  - HTTP server for web interface (configurable port)
  - TCP client connection to chat server (port 8080)
- Polls chat server for new messages
- Buffers messages and serves them to browser clients via HTTP
- Each client instance runs on its own HTTP port

## Running the Chat

### 1. Start the Chat Server

```bash
./compiler/c/bin/aislc examples/chat_app/chat_server.aisl
./compiler/c/bin/aisl-run examples/chat_app/chat_server.aislc
```

The server listens on port 8080.

### 2. Start Chat Clients

Each client needs its own HTTP port to avoid conflicts.

**First Client (port 3000):**
```bash
./compiler/c/bin/aislc examples/chat_app/chat_client.aisl
HTTP_PORT=3000 ./compiler/c/bin/aisl-run examples/chat_app/chat_client.aislc
```

**Second Client (port 3001):**
```bash
HTTP_PORT=3001 ./compiler/c/bin/aisl-run examples/chat_app/chat_client.aislc
```

**Third Client (port 3002):**
```bash
HTTP_PORT=3002 ./compiler/c/bin/aisl-run examples/chat_app/chat_client.aislc
```

### 3. Open in Browser

- Client 1: http://localhost:3000
- Client 2: http://localhost:3001
- Client 3: http://localhost:3002

All clients see the same chatroom and can communicate in real-time!

## Environment Variables

- `HTTP_PORT` - HTTP server port for the web interface (default: 3000)
- `CHAT_HOST` - Chat server hostname (default: localhost)

### Connecting to Remote Chat Server

```bash
CHAT_HOST=192.168.1.100 HTTP_PORT=3000 ./compiler/c/bin/aisl-run examples/chat_app/chat_client.aislc
```

## Features

- **Modern Web Interface** - Beautiful gradient UI with Tailwind CSS
- **Real-time Updates** - Automatic polling for new messages (500ms)
- **Multiple Clients** - Run multiple clients on the same machine
- **User Names** - Each user can set their own name
- **Message Broadcasting** - All messages are sent to all clients
- **System Messages** - Welcome messages when clients connect
- **Non-blocking I/O** - Efficient event-driven architecture

## API Endpoints

Each chat client HTTP server exposes:

- `GET /` - Web interface (serves chat.html)
- `GET /send?username=<name>&message=<text>` - Send a message
- `GET /poll?last=<index>` - Poll for new messages since index

## Technical Details

### Event Loop Architecture

The chat client uses a sophisticated event loop that monitors three types of sockets:
1. HTTP server socket (for new browser connections)
2. Chat server TCP connection (for incoming chat messages)
3. Active HTTP client sockets (for serving web requests)

```lisp
(loop
  ; Build inputs array: [http_server, chat_conn, ...http_clients]
  (set ready array (socket_select inputs))
  
  ; Handle ready sockets:
  ; - idx 0: new HTTP client (tcp_accept)
  ; - idx 1: message from chat server (tcp_receive)
  ; - idx 2+: HTTP request from browser (handle_http_client)
)
```

### Message Flow

1. Browser sends message via `/send` endpoint
2. Client forwards to chat server via TCP
3. Chat server broadcasts to all connected clients
4. Clients receive and buffer messages
5. Browser polls `/poll` endpoint to fetch new messages
6. JavaScript updates UI with new messages

## Example Multi-Client Session

**Terminal 1 - Server:**
```bash
./compiler/c/bin/aisl-run examples/chat_app/chat_server.aislc
# Chat server running on port 8080
```

**Terminal 2 - Alice's Client:**
```bash
HTTP_PORT=3000 ./compiler/c/bin/aisl-run examples/chat_app/chat_client.aislc
# HTTP interface running on http://localhost:3000
```

**Terminal 3 - Bob's Client:**
```bash
HTTP_PORT=3001 ./compiler/c/bin/aisl-run examples/chat_app/chat_client.aislc
# HTTP interface running on http://localhost:3001
```

**Browser:**
- Open http://localhost:3000 (Alice)
- Open http://localhost:3001 (Bob)
- Type messages in either window
- See them appear in both windows in real-time!

## Demonstrating AISL's Capabilities

This chat application showcases:
- **Non-blocking I/O** with `socket_select`
- **Multi-socket event loops** (HTTP + TCP simultaneously)
- **HTTP server implementation** with request parsing and routing
- **Message buffering and state management**
- **URL decoding** for query parameters
- **String manipulation** for parsing HTTP requests
- **Array operations** for managing multiple clients
- **Integration with external HTML/CSS/JS** via file loading
