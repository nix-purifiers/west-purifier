#include <stdio.h>
#include <stdlib.h>
#include "jsmn.h"
int main(void) {
 const char *json="42";
 jsmn_parser p; jsmn_init(&p); jsmntok_t tokens[4];
 if (jsmn_parse(&p,json,2,tokens,4) != 1) return 1;
 printf("%ld\n", strtol(json+tokens[0].start,0,10));
 return 0;
}
