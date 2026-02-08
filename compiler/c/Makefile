CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -pthread -g -Iinclude
LDFLAGS = -pthread -lm -lssl -lcrypto
# Note: Add -lsqlite3 once sqlite-devel is installed (dnf install sqlite-devel)

SRC_DIR = src
INC_DIR = include
BUILD_DIR = build
BIN_DIR = bin
EXAMPLES_DIR = ../../examples

# Compiler executable
COMPILER_SRCS = compiler.c lexer.c parser.c ast.c bytecode.c ast_export.c test_framework.c desugar.c module_loader.c
COMPILER_OBJS = $(addprefix $(BUILD_DIR)/, $(COMPILER_SRCS:.c=.o))
COMPILER = $(BIN_DIR)/aislc

# Runner executable
RUNNER_SRCS = runner.c bytecode.c vm.c runtime.c test_runner.c test_framework.c ast.c
RUNNER_OBJS = $(addprefix $(BUILD_DIR)/, $(RUNNER_SRCS:.c=.o))
RUNNER = $(BIN_DIR)/aisl-run

all: $(COMPILER) $(RUNNER)

$(COMPILER): $(COMPILER_OBJS) | $(BIN_DIR)
	$(CC) $(COMPILER_OBJS) -o $(COMPILER) $(LDFLAGS)

$(RUNNER): $(RUNNER_OBJS) | $(BIN_DIR)
	$(CC) $(RUNNER_OBJS) -o $(RUNNER) $(LDFLAGS)

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

clean:
	rm -f $(COMPILER_OBJS) $(RUNNER_OBJS) $(COMPILER) $(RUNNER)
	rm -f $(EXAMPLES_DIR)/*.aislc
	rm -rf $(BUILD_DIR) $(BIN_DIR)

.PHONY: all clean
