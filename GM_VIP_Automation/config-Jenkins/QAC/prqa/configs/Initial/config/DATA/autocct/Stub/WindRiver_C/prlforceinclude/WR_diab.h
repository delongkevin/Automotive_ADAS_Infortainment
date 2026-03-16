#ifndef WR_DIAB_H
#define WR_DIAB_H

/* Compilers may use another function within the assert macro to exit the 
 * program. QAC thus does not see an "exit" function and assumes the 
 * function returns, which it does not.
 * The below pragma tells QAC the compiler supplied function does not
 * return.
 */

/* examples - GCC, ICC, BCC 3.1, BCC 5.5, CYGWIN gcc, Watcom 1.6 */
#pragma PRQA_NO_RETURN __assert_fail
#pragma PRQA_NO_RETURN __assert_perror_fail
#pragma PRQA_NO_RETURN __assert

/* SDCC, BCC 5.5, Digital Mars DM 8.4, LCC, Watcom 1.6, Fujitsu F2MM,FR */
#pragma PRQA_NO_RETURN _assert

/* HI-TECH PCCLite */
#pragma PRQA_NO_RETURN _fassert

/* DJGPP, D.J.Delorie gcc DOS port */
#pragma PRQA_NO_RETURN __dj_assert

/* Watcom 1.6, MSVS 08 */
#pragma PRQA_NO_RETURN _wassert
#pragma PRQA_NO_RETURN __wassert
#pragma PRQA_NO_RETURN _assert99
#pragma PRQA_NO_RETURN _wassert99
#pragma PRQA_NO_RETURN __assert99
#pragma PRQA_NO_RETURN __wassert99

/* Renesas M32R compiler */
#pragma PRQA_NO_RETURN _Assert

/* NEC 78K0 series 16bit compiler */
#pragma PRQA_NO_RETURN __assertfail
#pragma PRQA_NO_RETURN __assertfail_n
#pragma PRQA_NO_RETURN __assertfail_f


/* Depending on the code that the compiler maker uses within the assert macro,
 * QAC may issue warnings. It is also possible that when the NDEBUG macro is used
 * to suppress the assertion code, QAC may issue a "no side-effects" warning.
 * To eliminate these, we turn off all warnings for the assert macro.
 */
#pragma PRQA_MACRO_MESSAGES_OFF "assert"


/* Any other items that may be required in a "force-include" file should be placed below. */
void *__alloca(int);
void __memory_barrier();
void __scheduling_barrier();
void *alloca(int);
int __builtin_expect(int, int);
int printf(const char *, ...);
int scanf(const char *, ...);
int sprintf(char *, const char *, ...);
int sscanf(const char *, const char *, ...);
void __builtin_prefetch(void *, ...);
void *__tls_varp(void *);

#ifdef __SPE__
typedef struct { unsigned short _f[4]; } __ev64_u16__;
typedef struct { short _f[4]; } __ev64_s16__;
typedef struct { unsigned int _f[2]; } __ev64_u32__;
typedef struct { int _f[2]; } __ev64_s32__;
typedef struct { unsigned long long _f[1]; } __ev64_u64__;
typedef struct { long long _f[1]; } __ev64_s64__;
typedef struct { float _f[2]; } __ev64_fs__;
typedef union {
  __ev64_u16__ _u16;
  __ev64_s16__ _s16;
  __ev64_u32__ _u32;
  __ev64_s32__ _s32;
  __ev64_u64__ _u64;
  __ev64_s64__ _s64;
  __ev64_fs__ _fs;
} __ev64_opaque__;
#endif

#else
#error "Multiple include"
#endif  /* ifndef WR_DIAB_H */

