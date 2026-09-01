/* libzcount.so — count & time zlib calls, dump stats on process exit.
 * Usage: LD_PRELOAD=libzcount.so:/path/to/real/libz.so.1
 */
#define _GNU_SOURCE
#include <zlib.h>
#include <errno.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

static double now(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + tv.tv_usec * 1e-6;
}

typedef unsigned long (*uLong_fn)(unsigned long, const unsigned char *, unsigned);
typedef int (*int_fn)(void);

#define STAT(name)  \
    static _Thread_local int name##_active; \
    static unsigned long name##_calls; \
    static double name##_time; \
    static void *name##_real;

STAT(deflate)
STAT(inflate)
STAT(adler32)
STAT(crc32)
STAT(compress2)
STAT(uncompress)

static void *get_real(const char *n, void **slot) {
    if (!*slot) {
        *slot = dlsym(RTLD_NEXT, n);
    }
    return *slot;
}

__attribute__((destructor)) static void dump(void) {
    char path[160];
    unsigned long long start = 0;
    FILE *st = fopen("/proc/self/stat", "r");
    if (st) {
        char buf[512];
        if (fgets(buf, sizeof buf, st)) {
            char *p2 = strrchr(buf, ')');
            if (p2) {
                unsigned long long fld[44 - 3 + 1];
                int nf = 0;
                for (char *t = strtok(p2 + 2, " "); t && nf < 42; t = strtok(NULL, " "))
                    fld[nf++] = strtoull(t, NULL, 10);
                if (nf >= 20) start = fld[19];
            }
        }
        fclose(st);
    }
    snprintf(path, sizeof path, "/tmp/zcount/%d-%llu-%s.log", (int)getpid(), start,
             strstr(program_invocation_name, "python") ? "python" : "other");
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "cmd=%s pid=%d\n", program_invocation_name, (int)getpid());
    fprintf(f, "deflate    calls=%lu time_ms=%.1f\n", deflate_calls, deflate_time * 1e3);
    fprintf(f, "inflate    calls=%lu time_ms=%.1f\n", inflate_calls, inflate_time * 1e3);
    fprintf(f, "adler32    calls=%lu time_ms=%.1f\n", adler32_calls, adler32_time * 1e3);
    fprintf(f, "crc32      calls=%lu time_ms=%.1f\n", crc32_calls, crc32_time * 1e3);
    fprintf(f, "compress2  calls=%lu time_ms=%.1f\n", compress2_calls, compress2_time * 1e3);
    fprintf(f, "uncompress calls=%lu time_ms=%.1f\n", uncompress_calls, uncompress_time * 1e3);
    fclose(f);
}

int deflate(z_streamp s, int f) {
    if (deflate_active) return ((int (*)(z_streamp, int))get_real("deflate", &deflate_real))(s, f);
    deflate_active = 1;
    double t0 = now();
    int r = ((int (*)(z_streamp, int))get_real("deflate", &deflate_real))(s, f);
    deflate_time += now() - t0;
    __atomic_fetch_add(&deflate_calls, 1, __ATOMIC_RELAXED);
    deflate_active = 0;
    return r;
}

int inflate(z_streamp s, int f) {
    if (inflate_active) return ((int (*)(z_streamp, int))get_real("inflate", &inflate_real))(s, f);
    inflate_active = 1;
    double t0 = now();
    int r = ((int (*)(z_streamp, int))get_real("inflate", &inflate_real))(s, f);
    inflate_time += now() - t0;
    __atomic_fetch_add(&inflate_calls, 1, __ATOMIC_RELAXED);
    inflate_active = 0;
    return r;
}

unsigned long adler32(unsigned long a, const unsigned char *b, unsigned l) {
    double t0 = now();
    unsigned long r = ((uLong_fn)get_real("adler32", &adler32_real))(a, b, l);
    adler32_time += now() - t0;
    __atomic_fetch_add(&adler32_calls, 1, __ATOMIC_RELAXED);
    return r;
}

unsigned long crc32(unsigned long a, const unsigned char *b, unsigned l) {
    double t0 = now();
    unsigned long r = ((uLong_fn)get_real("crc32", &crc32_real))(a, b, l);
    crc32_time += now() - t0;
    __atomic_fetch_add(&crc32_calls, 1, __ATOMIC_RELAXED);
    return r;
}

int compress2(unsigned char *d, unsigned long *dl, const unsigned char *s, unsigned long sl, int l) {
    double t0 = now();
    int r = ((int (*)(unsigned char *, unsigned long *, const unsigned char *, unsigned long, int))
        get_real("compress2", &compress2_real))(d, dl, s, sl, l);
    compress2_time += now() - t0;
    __atomic_fetch_add(&compress2_calls, 1, __ATOMIC_RELAXED);
    return r;
}

int uncompress(unsigned char *d, unsigned long *dl, const unsigned char *s, unsigned long sl) {
    double t0 = now();
    int r = ((int (*)(unsigned char *, unsigned long *, const unsigned char *, unsigned long))
        get_real("uncompress", &uncompress_real))(d, dl, s, sl);
    uncompress_time += now() - t0;
    __atomic_fetch_add(&uncompress_calls, 1, __ATOMIC_RELAXED);
    return r;
}
