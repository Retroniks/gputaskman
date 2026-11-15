#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>

static BOOL fill_private(id<MTLDevice> device, id<MTLBuffer> target, size_t count) {
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (!queue) return NO;
    id<MTLCommandBuffer> command = [queue commandBuffer];
    if (!command) return NO;
    id<MTLBlitCommandEncoder> encoder = [command blitCommandEncoder];
    if (!encoder) return NO;
    [encoder fillBuffer:target range:NSMakeRange(0, count) value:0x5a];
    [encoder endEncoding];
    [command commit];
    [command waitUntilCompleted];
    return command.status == MTLCommandBufferStatusCompleted;
}

int main(void) {
    alarm(80);  // Always release resources if the controller disappears.
    @autoreleasepool {
        id<MTLDevice> amd = nil;
        for (id<MTLDevice> candidate in MTLCopyAllDevices()) {
            if ([candidate.name rangeOfString:@"Radeon RX 580" options:NSCaseInsensitiveSearch].location != NSNotFound) {
                amd = candidate;
                break;
            }
        }
        if (!amd) { fprintf(stderr, "ERROR\tRX580_METAL_DEVICE_NOT_FOUND\n"); return 2; }
        const size_t step32 = (size_t)32 * 1024 * 1024;
        const size_t step64 = (size_t)64 * 1024 * 1024;
        id<MTLBuffer> first = [amd newBufferWithLength:step32 options:MTLResourceStorageModePrivate];
        if (!first || !fill_private(amd, first, step32)) {
            fprintf(stderr, "ERROR\tMETAL_32MiB_ALLOCATION_OR_COMMIT_FAILED\n"); return 3;
        }
        printf("STAGE\t32\t%ld\n", (long)getpid()); fflush(stdout);
        if (getchar() == EOF) return 4;
        id<MTLBuffer> second = [amd newBufferWithLength:step64 options:MTLResourceStorageModePrivate];
        if (!second || !fill_private(amd, second, step64)) {
            fprintf(stderr, "ERROR\tMETAL_96MiB_ALLOCATION_OR_COMMIT_FAILED\n"); return 5;
        }
        printf("STAGE\t96\t%ld\n", (long)getpid()); fflush(stdout);
        if (getchar() == EOF) return 6;
        // Exiting scope releases both buffers and command objects.
        printf("STAGE\tRELEASE\t%ld\n", (long)getpid()); fflush(stdout);
    }
    return 0;
}
