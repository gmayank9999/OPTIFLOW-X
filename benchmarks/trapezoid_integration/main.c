#include <stdio.h>
#include <math.h>

double f(double x) {
    return sin(x) * cos(x) + x * x * 0.001;
}

int main(void) {
    long n;
    double a, b;
    if (scanf("%ld %lf %lf", &n, &a, &b) != 3) return 1;

    double h = (b - a) / n;
    double sum = 0.5 * (f(a) + f(b));

    for (long i = 1; i < n; i++)
        sum += f(a + i * h);  /* strlen-like repeated recomputation of a+i*h each call */

    sum *= h;
    printf("%.6f\n", sum);
    return 0;
}
