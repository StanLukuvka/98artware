# Builds the things that go on the Windows 98 disk. The agent links
# without the mingw CRT because that CRT imports functions Windows 98 lacks.

MINGW   ?= i686-w64-mingw32-gcc
HOSTAS  ?= as
HOSTLD  ?= ld
HOSTOBJCOPY ?= objcopy
OUT     ?= build

CFLAGS  = -Os -march=i586 -mno-mmx -mno-sse -Wall -Wextra \
          -ffreestanding -fno-builtin -fno-stack-protector \
          -fno-asynchronous-unwind-tables -fno-unwind-tables \
          -fno-tree-loop-distribute-patterns -mno-stack-arg-probe
LDFLAGS = -nostdlib -nostartfiles -s -Wl,-e,_entry \
          -Wl,--subsystem,windows:4.0 \
          -Wl,--major-os-version,4 -Wl,--minor-os-version,0 \
          -Wl,--major-image-version,1 -Wl,--minor-image-version,0 \
          -Wl,--image-base,0x400000 -Wl,--section-alignment,4096 \
          -Wl,--file-alignment,512 -Wl,--disable-dynamicbase \
          -Wl,--disable-nxcompat \
          -Wl,--no-insert-timestamp
LIBS    = -lkernel32 -luser32 -lgdi32

all: $(OUT)/agent.exe $(OUT)/view.exe $(OUT)/mbr.bin

$(OUT)/agent.exe: agent.c | $(OUT)
	$(MINGW) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LIBS)

$(OUT)/view.exe: view.c | $(OUT)
	$(MINGW) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LIBS)

$(OUT)/mbr.bin: mbr.S | $(OUT)
	$(HOSTAS) --32 -o $(OUT)/mbr.o $<
	$(HOSTLD) -m elf_i386 -Ttext=0x600 -o $(OUT)/mbr.elf $(OUT)/mbr.o
	$(HOSTOBJCOPY) -O binary -j .text $(OUT)/mbr.elf $@

$(OUT):
	mkdir -p $@

clean:
	rm -rf $(OUT)

.PHONY: all clean
