INSTALL_DIR  := $(HOME)/.local/bin
SYSTEMD_DIR  := $(HOME)/.config/systemd/user
WORKDIR      := $(CURDIR)
CARGO        := cd crates && CARGO_BUILD_JOBS=1 cargo

BINS := yu-server gateway-server ai-coreutils yu
SVCS := yu-server gateway-server

.PHONY: build install deploy enable restart status logs

build:
	$(CARGO) build --release

install: build
	mkdir -p $(INSTALL_DIR)
	$(foreach b,$(BINS),cp crates/target/release/$(b) $(INSTALL_DIR)/$(b);)

deploy: install
	mkdir -p $(SYSTEMD_DIR)
	$(foreach s,$(SVCS), \
		sed "s|__WORKDIR__|$(WORKDIR)|g" deploy/systemd/$(s).service \
		> $(SYSTEMD_DIR)/$(s).service;)
	systemctl --user daemon-reload

enable: deploy
	$(foreach s,$(SVCS),systemctl --user enable --now $(s);)

restart:
	$(foreach s,$(SVCS),systemctl --user restart $(s);)

status:
	systemctl --user status $(SVCS)

logs:
	journalctl --user -u yu-server -f
