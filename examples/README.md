# AISL Examples

Practical examples demonstrating AISL capabilities.

## Available Examples

### Basic Examples

- **hello_world.aisl** - Classic "Hello, World!" program

### Web Applications

- **todo_app/** - Full-featured TODO app with SQLite database
  - Complete CRUD operations
  - Database persistence
  - Modern web interface
  - See `todo_app/README.md` for details

- **chat_app/** - Real-time chat application with WebSocket
  - WebSocket server and client
  - HTML frontend
  - See `chat_app/README.md` for details

## Running Examples

Run any example directly:

```bash
./interpreter/_build/default/vm.exe examples/hello_world.aisl
```

For web applications:

```bash
# Run TODO app
./interpreter/_build/default/vm.exe examples/todo_app/todo_app.aisl

# Run chat server
./interpreter/_build/default/vm.exe examples/chat_app/chat_server.aisl
```

## Contributing Examples

When adding examples:
1. Use descriptive names
2. Keep examples focused on one feature
3. Add entry to this README
4. Ensure example runs correctly
