#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main(void) {
    int n, steps;
    if (scanf("%d %d", &n, &steps) != 2) return 1;

    double *x = malloc(sizeof(double) * n), *y = malloc(sizeof(double) * n), *z = malloc(sizeof(double) * n);
    double *vx = calloc(n, sizeof(double)), *vy = calloc(n, sizeof(double)), *vz = calloc(n, sizeof(double));
    double *mass = malloc(sizeof(double) * n);
    double dt = 0.001, eps = 1e-6;

    for (int i = 0; i < n; i++) {
        x[i] = (i % 53) * 0.5; y[i] = (i % 47) * 0.5; z[i] = (i % 41) * 0.5;
        mass[i] = 1.0 + (i % 5) * 0.1;
    }

    for (int s = 0; s < steps; s++) {
        for (int i = 0; i < n; i++) {
            double fx = 0, fy = 0, fz = 0;
            for (int j = 0; j < n; j++) {
                if (i == j) continue;
                double dx = x[j] - x[i], dy = y[j] - y[i], dz = z[j] - z[i];
                double dist2 = dx * dx + dy * dy + dz * dz + eps;
                double inv_dist3 = 1.0 / (dist2 * sqrt(dist2));
                fx += mass[j] * dx * inv_dist3;
                fy += mass[j] * dy * inv_dist3;
                fz += mass[j] * dz * inv_dist3;
            }
            vx[i] += dt * fx; vy[i] += dt * fy; vz[i] += dt * fz;
        }
        for (int i = 0; i < n; i++) {
            x[i] += dt * vx[i]; y[i] += dt * vy[i]; z[i] += dt * vz[i];
        }
    }

    double sum = 0;
    for (int i = 0; i < n; i++) sum += x[i] + y[i] + z[i];
    printf("%.6f\n", sum);

    free(x); free(y); free(z); free(vx); free(vy); free(vz); free(mass);
    return 0;
}
