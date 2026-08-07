/*#include <zephyr/kernel.h>
#include <string.h>
#define SLEEP_TIME 375

int uptime_worker_main(){
    uint_64_t tmp;
    char ch_buf[20];
    while(1){
    
        tmp = k_uptime_get();		
        sprintf(c_buf, "%lu", tmp);

        Message msg = {
            .message_type = DEFAULT_MSG;
            .len = strlen(ch_buf);
            .str_data = ch_buf;
        };

        //
        //TODO! 
        //Make send a uptime via DECT
        k_msleep(SLEEP_TIME);
    }
}
*/