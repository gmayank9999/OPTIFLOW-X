#include <stdio.h>
#include <stdlib.h>

typedef struct {
    int id;
    char name[48];
    double salary;
    double bonus;
    int dept;
    int years;
    char notes[64];
} Employee;

int main(void) {
    int n, passes;
    if (scanf("%d %d", &n, &passes) != 2) return 1;

    Employee *emp = malloc(sizeof(Employee) * (size_t)n);
    for (int i = 0; i < n; i++) {
        emp[i].id = i;
        emp[i].salary = 30000.0 + (i % 97) * 137.0;
        emp[i].bonus = (i % 13) * 50.0;
        emp[i].dept = i % 8;
        emp[i].years = i % 20;
    }

    double total = 0;
    for (int p = 0; p < passes; p++)
        for (int i = 0; i < n; i++)
            total += emp[i].salary;   /* one field touched out of a much larger record */

    printf("%.6f\n", total);

    free(emp);
    return 0;
}
