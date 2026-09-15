SSL_PREFIX ?= /usr/local/ssl
PREFIX ?= /usr
CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Werror
LDFLAGS ?=

BIN = openssl-fips-test

all: $(BIN)

$(BIN): openssl-fips-test.c
	$(CC) $(CFLAGS) -I$(SSL_PREFIX)/include -o $@ $< \
		$(LDFLAGS) -L$(SSL_PREFIX)/lib -Wl,-rpath,$(SSL_PREFIX)/lib -lcrypto

install: $(BIN)
	install -D -m 0755 $(BIN) $(DESTDIR)$(PREFIX)/bin/$(BIN)

clean:
	rm -f $(BIN)

.PHONY: all install clean
