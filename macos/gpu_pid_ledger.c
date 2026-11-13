/* Bounded read-only Mach graphics-ledger probe. Values are NOT discrete VRAM. */
#include <mach/mach.h>
#include <mach/task_info.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static void probe(pid_t pid) {
    mach_port_t task = MACH_PORT_NULL;
    int own = (pid == getpid());
    kern_return_t kr = KERN_SUCCESS;
    if (own) {
        task = mach_task_self();
    } else {
        kr = task_for_pid(mach_task_self(), pid, &task);
    }
    if (kr != KERN_SUCCESS || task == MACH_PORT_NULL) {
        printf("%ld\ttask_port_%d\t-1\t-1\n", (long)pid, (int)kr);
        return;
    }
    task_vm_info_data_t info = {0};
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    kr = task_info(task, TASK_VM_INFO, (task_info_t)&info, &count);
    if (kr == KERN_SUCCESS && count >= TASK_VM_INFO_REV3_COUNT) {
        printf("%ld\tok\t%lld\t%llu\n", (long)pid,
               (long long)info.ledger_tag_graphics_footprint,
               (unsigned long long)info.device);
    } else {
        printf("%ld\ttask_info_%d_count_%u\t-1\t-1\n", (long)pid,
               (int)kr, (unsigned)count);
    }
    if (!own) mach_port_deallocate(mach_task_self(), task);
}
int main(int argc, char **argv) {
    if (argc == 1) { probe(getpid()); return 0; }
    for (int i = 1; i < argc; ++i) {
        char *end = NULL;
        long value = strtol(argv[i], &end, 10);
        if (end == argv[i] || *end != '\0' || value <= 0 || value > 2147483647L) return 2;
        probe((pid_t)value);
    }
    return 0;
}
