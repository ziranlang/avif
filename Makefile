.PHONY: all test native-tools
PYTHON ?= python3
all: build/bin/avif-native
native-tools: build/native-tools/.requirements.stamp
build/native-tools/.requirements.stamp: native/requirements.txt
	mkdir -p build/native-tools
	$(PYTHON) -m pip install --disable-pip-version-check --upgrade --target build/native-tools -r $<
	touch $@
build/bin/avif-native: native/provider.py Makefile build/native-tools/.requirements.stamp
	mkdir -p build/bin
	@set -e; stage=$$(mktemp build/bin/.avif-native.XXXXXX); \
	trap 'rm -f "$$stage"' EXIT HUP INT TERM; \
	install -m 755 native/provider.py "$$stage"; \
	mv -f "$$stage" $@
test:
	build-queue -- sh tests/avif.sh
