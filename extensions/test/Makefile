# Makefile for AISL test extension

CC = gcc
CFLAGS = -Wall -Wextra -fPIC -std=c11
LDFLAGS = -shared

TARGET = libaisl_test.so
SRC = test.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $(TARGET) $(SRC)

clean:
	rm -f $(TARGET)

install:
	mkdir -p ../../extensions
	cp $(TARGET) ../../extensions/

.PHONY: all clean install
