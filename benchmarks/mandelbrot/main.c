#include <stdio.h>

int main(void) {
    int w, h, maxiter;
    if (scanf("%d %d %d", &w, &h, &maxiter) != 3) return 1;

    double xmin = -2.0, xmax = 1.0, ymin = -1.5, ymax = 1.5;
    long long total = 0;

    for (int py = 0; py < h; py++) {
        double cy = ymin + (ymax - ymin) * py / (h > 1 ? (h - 1) : 1);
        for (int px = 0; px < w; px++) {
            double cx = xmin + (xmax - xmin) * px / (w > 1 ? (w - 1) : 1);
            double x = 0, y = 0;
            int it = 0;
            while (x * x + y * y <= 4.0 && it < maxiter) {
                double xt = x * x - y * y + cx;
                y = 2 * x * y + cy;
                x = xt;
                it++;
            }
            total += it;
        }
    }

    printf("%lld\n", total);
    return 0;
}
