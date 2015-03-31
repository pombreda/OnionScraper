	.file	"bounds.c"
# GNU C (Ubuntu 4.9.1-16ubuntu6) version 4.9.1 (x86_64-linux-gnu)
#	compiled by GNU C version 4.9.1, GMP version 6.0.0, MPFR version 3.1.2-p3, MPC version 1.0.2
# GGC heuristics: --param ggc-min-expand=100 --param ggc-min-heapsize=131072
# options passed:  -nostdinc -I /usr/src/linux-headers-lbm-
# -I /build/buildd/linux-3.16.0/arch/x86/include
# -I arch/x86/include/generated -I /build/buildd/linux-3.16.0/include
# -I include -I /build/buildd/linux-3.16.0/arch/x86/include/uapi
# -I arch/x86/include/generated/uapi
# -I /build/buildd/linux-3.16.0/include/uapi -I include/generated/uapi
# -I ubuntu/include -I /build/buildd/linux-3.16.0/ubuntu/include
# -I /build/buildd/linux-3.16.0/. -I . -imultiarch x86_64-linux-gnu
# -D __KERNEL__ -D CONFIG_X86_X32_ABI -D CONFIG_AS_CFI=1
# -D CONFIG_AS_CFI_SIGNAL_FRAME=1 -D CONFIG_AS_CFI_SECTIONS=1
# -D CONFIG_AS_FXSAVEQ=1 -D CONFIG_AS_CRC32=1 -D CONFIG_AS_AVX=1
# -D CONFIG_AS_AVX2=1 -D CC_USING_FENTRY -D CC_HAVE_ASM_GOTO
# -D KBUILD_STR(s)=#s -D KBUILD_BASENAME=KBUILD_STR(bounds)
# -D KBUILD_MODNAME=KBUILD_STR(bounds)
# -isystem /usr/lib/gcc/x86_64-linux-gnu/4.9/include
# -include /build/buildd/linux-3.16.0/include/linux/kconfig.h
# -MD kernel/.bounds.s.d /build/buildd/linux-3.16.0/kernel/bounds.c -m64
# -mno-80387 -mno-fp-ret-in-387 -mpreferred-stack-boundary=3 -mtune=generic
# -mno-red-zone -mcmodel=kernel -maccumulate-outgoing-args -mno-sse
# -mno-mmx -mno-sse2 -mno-3dnow -mno-avx -mfentry -march=x86-64
# -auxbase-strip kernel/bounds.s -O2 -Wall -Wundef -Wstrict-prototypes
# -Wno-trigraphs -Werror=implicit-function-declaration -Wno-format-security
# -Wno-sign-compare -Wframe-larger-than=1024 -Wno-unused-but-set-variable
# -Wdeclaration-after-statement -Wno-pointer-sign -Werror=implicit-int
# -Werror=strict-prototypes -Werror=date-time -p -fno-strict-aliasing
# -fno-common -funit-at-a-time -fno-asynchronous-unwind-tables
# -fno-delete-null-pointer-checks -fstack-protector -fno-omit-frame-pointer
# -fno-optimize-sibling-calls -fno-var-tracking-assignments
# -fno-inline-functions-called-once -fno-strict-overflow -fconserve-stack
# -fverbose-asm
# options enabled:  -faggressive-loop-optimizations -fauto-inc-dec
# -fbranch-count-reg -fcaller-saves -fcombine-stack-adjustments
# -fcompare-elim -fcprop-registers -fcrossjumping -fcse-follow-jumps
# -fdefer-pop -fdevirtualize -fdevirtualize-speculatively -fdwarf2-cfi-asm
# -fearly-inlining -feliminate-unused-debug-types -fexpensive-optimizations
# -fforward-propagate -ffunction-cse -fgcse -fgcse-lm -fgnu-runtime
# -fgnu-unique -fguess-branch-probability -fhoist-adjacent-loads -fident
# -fif-conversion -fif-conversion2 -findirect-inlining -finline
# -finline-atomics -finline-small-functions -fipa-cp -fipa-profile
# -fipa-pure-const -fipa-reference -fipa-sra -fira-hoist-pressure
# -fira-share-save-slots -fira-share-spill-slots
# -fisolate-erroneous-paths-dereference -fivopts -fkeep-static-consts
# -fleading-underscore -fmath-errno -fmerge-constants -fmerge-debug-strings
# -fmove-loop-invariants -foptimize-strlen -fpartial-inlining -fpeephole
# -fpeephole2 -fprefetch-loop-arrays -fprofile -free -freg-struct-return
# -freorder-blocks -freorder-blocks-and-partition -freorder-functions
# -frerun-cse-after-loop -fsched-critical-path-heuristic
# -fsched-dep-count-heuristic -fsched-group-heuristic -fsched-interblock
# -fsched-last-insn-heuristic -fsched-rank-heuristic -fsched-spec
# -fsched-spec-insn-heuristic -fsched-stalled-insns-dep -fschedule-insns2
# -fshow-column -fshrink-wrap -fsigned-zeros -fsplit-ivs-in-unroller
# -fsplit-wide-types -fstack-protector -fstrict-volatile-bitfields
# -fsync-libcalls -fthread-jumps -ftoplevel-reorder -ftrapping-math
# -ftree-bit-ccp -ftree-builtin-call-dce -ftree-ccp -ftree-ch
# -ftree-coalesce-vars -ftree-copy-prop -ftree-copyrename -ftree-cselim
# -ftree-dce -ftree-dominator-opts -ftree-dse -ftree-forwprop -ftree-fre
# -ftree-loop-if-convert -ftree-loop-im -ftree-loop-ivcanon
# -ftree-loop-optimize -ftree-parallelize-loops= -ftree-phiprop -ftree-pre
# -ftree-pta -ftree-reassoc -ftree-scev-cprop -ftree-sink -ftree-slsr
# -ftree-sra -ftree-switch-conversion -ftree-tail-merge -ftree-ter
# -ftree-vrp -funit-at-a-time -fverbose-asm -fzero-initialized-in-bss
# -m128bit-long-double -m64 -maccumulate-outgoing-args -malign-stringops
# -mavx256-split-unaligned-load -mavx256-split-unaligned-store -mfentry
# -mfxsr -mglibc -mieee-fp -mlong-double-80 -mno-fancy-math-387
# -mno-red-zone -mno-sse4 -mpush-args -mtls-direct-seg-refs -mvzeroupper

	.section	.text.unlikely,"ax",@progbits
.LCOLDB0:
	.text
.LHOTB0:
	.p2align 4,,15
	.globl	foo
	.type	foo, @function
foo:
	call	__fentry__
	pushq	%rbp	#
	movq	%rsp, %rbp	#,
#APP
# 19 "/build/buildd/linux-3.16.0/kernel/bounds.c" 1
	
->NR_PAGEFLAGS $25 __NR_PAGEFLAGS	#
# 0 "" 2
# 20 "/build/buildd/linux-3.16.0/kernel/bounds.c" 1
	
->MAX_NR_ZONES $4 __MAX_NR_ZONES	#
# 0 "" 2
# 21 "/build/buildd/linux-3.16.0/kernel/bounds.c" 1
	
->NR_PCG_FLAGS $3 __NR_PCG_FLAGS	#
# 0 "" 2
# 23 "/build/buildd/linux-3.16.0/kernel/bounds.c" 1
	
->NR_CPUS_BITS $8 ilog2(CONFIG_NR_CPUS)	#
# 0 "" 2
# 25 "/build/buildd/linux-3.16.0/kernel/bounds.c" 1
	
->SPINLOCK_SIZE $4 sizeof(spinlock_t)	#
# 0 "" 2
#NO_APP
	popq	%rbp	#
	ret
	.size	foo, .-foo
	.section	.text.unlikely
.LCOLDE0:
	.text
.LHOTE0:
	.ident	"GCC: (Ubuntu 4.9.1-16ubuntu6) 4.9.1"
	.section	.note.GNU-stack,"",@progbits
