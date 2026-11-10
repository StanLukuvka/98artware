# Master boot record for the install disk. A blank MBR will not boot, and
# Windows 98 Setup only writes the partition's boot sector, so the setup tool
# supplies this. Finds the active partition, loads its first sector with the
# INT 13h extensions and chains to it.

.code16
.text
.globl _start
_start:
    cli
    xor  %ax, %ax
    mov  %ax, %ds
    mov  %ax, %es
    mov  %ax, %ss
    mov  $0x7c00, %sp
    sti
    cld
    mov  $0x7c00, %si
    mov  $0x0600, %di
    mov  $256, %cx
    rep  movsw
    ljmp $0, $reloc

reloc:
    mov  $0x07be, %si
    mov  $4, %cx
find:
    testb $0x80, (%si)
    jnz  found
    add  $16, %si
    loop find
    jmp  fail

found:
    mov  %si, %bp
    mov  8(%si), %ax
    mov  %ax, dap_lba
    mov  10(%si), %ax
    mov  %ax, dap_lba + 2
    mov  $dap, %si
    mov  $0x42, %ah
    int  $0x13
    jc   fail
    cmpw $0xaa55, 0x7dfe
    jne  fail
    mov  %bp, %si
    ljmp $0, $0x7c00

fail:
    mov  $msg, %si
print:
    lodsb
    test %al, %al
    jz   halt
    mov  $0x0e, %ah
    mov  $7, %bx
    int  $0x10
    jmp  print
halt:
    hlt
    jmp  halt

msg:
    .asciz "art98: no bootable partition"

.balign 4
dap:
    .byte 16, 0
    .word 1
    .word 0x7c00, 0
dap_lba:
    .long 0, 0
