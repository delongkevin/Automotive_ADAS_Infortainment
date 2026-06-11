PRIVATE_DIR := ../Private

# build
hwioappl hwioboot hwiorpgm:
	@case $@ in \
	hwioappl)  dir=HWIOAPPL;  kind=APPL ;; \
	hwioboot)  dir=HWIOBOOT;  kind=BOOT ;; \
	hwiorpgm)  dir=HWIORPGM;  kind=RPGM ;; \
	esac; \
	target=$@; \
	for f in $(PRIVATE_DIR)/*.makefile; do \
	  [ -e "$$f" ] || continue; \
	  echo "$$f" | grep -q "$$kind" || continue; \
	  $(MAKE) -f $$f -C $(PRIVATE_DIR) $$target -j -B; \
	done; \
	$(MAKE) -C $$dir $$target -j -B;

# clean
clean_hwioappl clean_hwioboot clean_hwiorpgm:
	@case $@ in \
	  clean_hwioappl) dir=HWIOAPPL; kind=APPL ;; \
	  clean_hwioboot) dir=HWIOBOOT; kind=BOOT ;; \
	  clean_hwiorpgm) dir=HWIORPGM; kind=RPGM ;; \
	esac; \
	target=$@; \
	for f in $(PRIVATE_DIR)/*.makefile; do \
	  [ -e "$$f" ] || continue; \
	  echo "$$f" | grep -q "$$kind" || continue; \
	$(MAKE) -f $$f -C $(PRIVATE_DIR) $$target -j -B; \
	done; \
	$(MAKE) -C $$dir $$target -j -B;

# test build
Magna_testhwioappl Magna_testhwioboot Magna_testhwiorpgm:
	@case $@ in \
	  Magna_testhwioappl)  dir=HWIOAPPL; kind=APPL ;; \
	  Magna_testhwioboot)  dir=HWIOBOOT; kind=BOOT ;; \
	  Magna_testhwiorpgm)  dir=HWIORPGM; kind=RPGM ;; \
	esac; \
	target=$@; \
	for f in $(PRIVATE_DIR)/*.makefile; do \
	  [ -e "$$f" ] || continue; \
	  echo "$$f" | grep -q "$$kind" || continue; \
	  $(MAKE) -f $$f -C $(PRIVATE_DIR) $$target -j -B; \
	done; \
	$(MAKE) -C $$dir $$target -j -B;

# clean test
clean_testhwioappl clean_testhwioboot clean_testhwiorpgm:
	@case $@ in \
	  clean_testhwioappl) dir=HWIOAPPL; kind=APPL ;; \
	  clean_testhwioboot) dir=HWIOBOOT; kind=BOOT ;; \
	  clean_testhwiorpgm) dir=HWIORPGM; kind=RPGM ;; \
	esac; \
	target=$@; \
	for f in $(PRIVATE_DIR)/*.makefile; do \
	  [ -e "$$f" ] || continue; \
	  echo "$$f" | grep -q "$$kind" || continue; \
	  $(MAKE) -f $$f -C $(PRIVATE_DIR) $$target -j -B; \
	done; \
	$(MAKE) -C $$dir $$target -j -B;
