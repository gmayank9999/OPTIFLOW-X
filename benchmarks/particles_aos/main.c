#include <stdio.h>
#include <stdlib.h>

typedef struct {
    double x, y, z;
    double vx, vy, vz;
    double mass, charge;
} Particle;

int main(void) {
    int n, steps;
    double dt;
    if (scanf("%d %d %lf", &n, &steps, &dt) != 3) return 1;

    Particle *p = malloc(sizeof(Particle) * (size_t)n);
    for (int i = 0; i < n; i++) {
        p[i].x = (i % 97) * 0.1; p[i].y = (i % 89) * 0.1; p[i].z = (i % 83) * 0.1;
        p[i].vx = (i % 13) * 0.01; p[i].vy = (i % 17) * 0.01; p[i].vz = (i % 19) * 0.01;
        p[i].mass = 1.0; p[i].charge = 0.0;
    }

    for (int s = 0; s < steps; s++)
        for (int i = 0; i < n; i++) {
            p[i].x += p[i].vx * dt;  /* touches 3 of 8 fields: rest of the struct rides along in cache */
            p[i].y += p[i].vy * dt;
            p[i].z += p[i].vz * dt;
        }

    double sum = 0;
    for (int i = 0; i < n; i++) sum += p[i].x + p[i].y + p[i].z;
    printf("%.6f\n", sum);

    free(p);
    return 0;
}
