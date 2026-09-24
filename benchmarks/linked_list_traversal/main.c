#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *next;
} Node;

int main(void) {
    int n, passes;
    if (scanf("%d %d", &n, &passes) != 2) return 1;

    Node *head = NULL, *tail = NULL;
    for (int i = 0; i < n; i++) {
        Node *node = malloc(sizeof(Node));   /* scattered allocations: no locality between nodes */
        node->value = (i % 991) - 495;
        node->next = NULL;
        if (!head) head = node; else tail->next = node;
        tail = node;
    }

    long long sum = 0;
    for (int p = 0; p < passes; p++) {
        Node *cur = head;
        while (cur) {
            sum += cur->value;
            cur = cur->next;
        }
    }

    printf("%lld\n", sum);

    Node *cur = head;
    while (cur) { Node *next = cur->next; free(cur); cur = next; }
    return 0;
}
