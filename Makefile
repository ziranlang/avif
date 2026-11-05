.PHONY: all test
all: build/bin/avif-native
build/bin/avif-native: native/provider.py Makefile
	mkdir -p build/bin
	@set -e; stage=$$(mktemp build/bin/.avif-native.XXXXXX); \
	trap 'rm -f "$$stage"' EXIT HUP INT TERM; \
	install -m 755 native/provider.py "$$stage"; \
	mv -f "$$stage" $@
test:
	build-queue -- sh tests/avif.sh
