/*
 * hrtime: high-resolution benchmark harness baked into the sandbox image.
 *
 *   hrtime <runs> <warmup> <input_file> <prog> [<prog> ...]
 *
 * For each round (warmup rounds first, then timed rounds) it runs every
 * listed program once, in order, with stdin redirected from <input_file>
 * and stdout sent to /dev/null. Interleaving programs round by round
 * (A B A B ...) means slow drift on the host -- thermal throttling, a
 * background process waking up -- hits baseline and candidate alike
 * instead of biasing whichever happened to run second.
 *
 * One line per timed run on stdout:
 *
 *   <prog_index> <wall_ms> <cpu_ms> <maxrss_kb> <exit_status>
 *
 * wall_ms comes from CLOCK_MONOTONIC (nanosecond resolution, versus the
 * 10 ms of /usr/bin/time); cpu_ms and maxrss_kb from wait4()'s rusage.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}

static int run_once(const char *prog, const char *input, double *wall_ms,
                    double *cpu_ms, long *maxrss_kb) {
    double t0 = now_ms();
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        int in = open(input, O_RDONLY);
        int out = open("/dev/null", O_WRONLY);
        if (in < 0 || out < 0) _exit(127);
        dup2(in, STDIN_FILENO);
        dup2(out, STDOUT_FILENO);
        close(in);
        close(out);
        execl(prog, prog, (char *)NULL);
        _exit(127);
    }
    int status = 0;
    struct rusage ru;
    if (wait4(pid, &status, 0, &ru) < 0) return -1;
    *wall_ms = now_ms() - t0;
    *cpu_ms = (ru.ru_utime.tv_sec + ru.ru_stime.tv_sec) * 1e3 +
              (ru.ru_utime.tv_usec + ru.ru_stime.tv_usec) / 1e3;
    *maxrss_kb = ru.ru_maxrss;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}

int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr, "usage: %s <runs> <warmup> <input> <prog> [<prog>...]\n", argv[0]);
        return 2;
    }
    int runs = atoi(argv[1]);
    int warmup = atoi(argv[2]);
    const char *input = argv[3];
    int nprogs = argc - 4;

    for (int round = 0; round < warmup + runs; round++) {
        for (int p = 0; p < nprogs; p++) {
            double wall, cpu;
            long rss;
            int rc = run_once(argv[4 + p], input, &wall, &cpu, &rss);
            if (round >= warmup) {
                printf("%d %.4f %.4f %ld %d\n", p, wall, cpu, rss, rc);
                fflush(stdout);
            }
        }
    }
    return 0;
}
