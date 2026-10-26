// SPDX-License-Identifier: GPL-3.0-or-later
// bc250-ace-test: checks that the dedicated compute (ACE) queues of the GPU work, on every queue at once.
//
//   bc250-ace-test [--rounds N] [--any-queue]
//
// Each round makes a new Vulkan device with all the queues of the dedicated compute family and gives every
// queue the same job: a buffer fill, a buffer copy, a copy from a buffer into an image and back (RADV runs these
// with its own copy shaders, where the GFX1013 bug dropped rows), and a dispatch whose last workgroup is a
// partial one. The results are compared word for word; the device is then destroyed, so the rounds also repeat
// the queues' setup and teardown. --any-queue uses any queue with compute, for trying the test on another driver.
//
// Exit status: 0 passed, 1 wrong data, 2 Vulkan error, 3 no dedicated compute queue family, 4 a queue did not
// finish within the time limit (a GPU hang is likely; see the kernel log).
#include <vulkan/vulkan.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const uint32_t shader_code[] =
#include "ace-test.spv.inc"
;

#define BUFFER_SIZE (4u << 20)          // above RADV's 4 KiB threshold, so fills and copies run as shaders
#define IMAGE_W 1000u                   // not a multiple of 8: the copy shaders' last workgroups are partial
#define IMAGE_H 777u
#define DISPATCH_COUNT 1000003u         // not a multiple of 64
#define FENCE_TIMEOUT_NS (30ull * 1000 * 1000 * 1000)

#define EXIT_DATA 1
#define EXIT_VULKAN 2
#define EXIT_NO_ACE 3
#define EXIT_TIMEOUT 4

#define CHECK(call)                                                                       \
    do {                                                                                  \
        VkResult r_ = (call);                                                             \
        if (r_ != VK_SUCCESS) {                                                           \
            printf("FAIL: %s returned VkResult %d (line %d)\n", #call, (int)r_, __LINE__); \
            exit(r_ == VK_ERROR_DEVICE_LOST ? EXIT_TIMEOUT : EXIT_VULKAN);                \
        }                                                                                 \
    } while (0)

struct buffer {
    VkBuffer buffer;
    VkDeviceMemory memory;
    uint32_t *data;
};

struct job {
    VkQueue queue;
    VkCommandBuffer cmd;
    VkFence fence;
    VkDescriptorSet set;
    struct buffer src, fill, copy, back, out;
    VkImage image;
    VkDeviceMemory image_memory;
    uint32_t seed;
};

static VkPhysicalDevice gpu;
static VkDevice dev;
static VkPhysicalDeviceMemoryProperties mem_props;

static uint32_t pattern(uint32_t i, uint32_t seed) { return (i * 2654435761u) ^ seed; }

// The shader's value, computed on the CPU.
static uint32_t expected(uint32_t i, uint32_t seed)
{
    uint32_t v = i ^ seed;
    for (int k = 0; k < 16; ++k)
        v = v * 1664525u + 1013904223u;
    return v;
}

static uint32_t memory_type(uint32_t bits, VkMemoryPropertyFlags want)
{
    for (uint32_t i = 0; i < mem_props.memoryTypeCount; ++i)
        if ((bits & (1u << i)) && (mem_props.memoryTypes[i].propertyFlags & want) == want)
            return i;
    printf("FAIL: no memory type with flags 0x%x\n", want);
    exit(EXIT_VULKAN);
}

static VkDeviceMemory allocate(VkMemoryRequirements req, VkMemoryPropertyFlags want)
{
    VkMemoryAllocateInfo info = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = req.size,
        .memoryTypeIndex = memory_type(req.memoryTypeBits, want),
    };
    VkDeviceMemory memory;
    CHECK(vkAllocateMemory(dev, &info, NULL, &memory));
    return memory;
}

static struct buffer make_buffer(VkBufferUsageFlags usage)
{
    struct buffer b;
    VkBufferCreateInfo info = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = BUFFER_SIZE,
        .usage = usage,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
    };
    CHECK(vkCreateBuffer(dev, &info, NULL, &b.buffer));
    VkMemoryRequirements req;
    vkGetBufferMemoryRequirements(dev, b.buffer, &req);
    b.memory = allocate(req, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    CHECK(vkBindBufferMemory(dev, b.buffer, b.memory, 0));
    CHECK(vkMapMemory(dev, b.memory, 0, BUFFER_SIZE, 0, (void **)&b.data));
    memset(b.data, 0, BUFFER_SIZE);
    return b;
}

static void free_buffer(struct buffer *b)
{
    vkUnmapMemory(dev, b->memory);
    vkDestroyBuffer(dev, b->buffer, NULL);
    vkFreeMemory(dev, b->memory, NULL);
}

static void image_barrier(VkCommandBuffer cmd, VkImage image, VkImageLayout from, VkImageLayout to,
                          VkAccessFlags src_access, VkAccessFlags dst_access)
{
    VkImageMemoryBarrier barrier = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .srcAccessMask = src_access,
        .dstAccessMask = dst_access,
        .oldLayout = from,
        .newLayout = to,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = image,
        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1},
    };
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL,
                         1, &barrier);
}

static void record(struct job *j, VkPipeline pipeline, VkPipelineLayout layout)
{
    VkCommandBufferBeginInfo begin = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
    };
    CHECK(vkBeginCommandBuffer(j->cmd, &begin));

    vkCmdFillBuffer(j->cmd, j->fill.buffer, 0, BUFFER_SIZE, j->seed);
    VkBufferCopy whole = {0, 0, BUFFER_SIZE};
    vkCmdCopyBuffer(j->cmd, j->src.buffer, j->copy.buffer, 1, &whole);

    VkBufferImageCopy region = {
        .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
        .imageExtent = {IMAGE_W, IMAGE_H, 1},
    };
    image_barrier(j->cmd, j->image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0,
                  VK_ACCESS_TRANSFER_WRITE_BIT);
    vkCmdCopyBufferToImage(j->cmd, j->src.buffer, j->image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
    image_barrier(j->cmd, j->image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                  VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
    vkCmdCopyImageToBuffer(j->cmd, j->image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, j->back.buffer, 1, &region);

    uint32_t push[2] = {DISPATCH_COUNT, j->seed};
    vkCmdBindPipeline(j->cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
    vkCmdBindDescriptorSets(j->cmd, VK_PIPELINE_BIND_POINT_COMPUTE, layout, 0, 1, &j->set, 0, NULL);
    vkCmdPushConstants(j->cmd, layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(push), push);
    vkCmdDispatch(j->cmd, (DISPATCH_COUNT + 63) / 64, 1, 1);

    VkMemoryBarrier to_host = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_SHADER_WRITE_BIT,
        .dstAccessMask = VK_ACCESS_HOST_READ_BIT,
    };
    vkCmdPipelineBarrier(j->cmd, VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                         VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &to_host, 0, NULL, 0, NULL);
    CHECK(vkEndCommandBuffer(j->cmd));
}

// Compares *n* words; prints the first wrong one. Returns the number of wrong words.
static uint32_t compare(const char *what, int queue, const uint32_t *got, const uint32_t *want, uint32_t n)
{
    uint32_t wrong = 0;
    for (uint32_t i = 0; i < n; ++i) {
        if (got[i] == want[i])
            continue;
        if (!wrong++)
            printf("  queue %d, %s: word %" PRIu32 " is 0x%08" PRIx32 ", expected 0x%08" PRIx32 "\n", queue, what, i,
                   got[i], want[i]);
    }
    if (wrong)
        printf("  queue %d, %s: %" PRIu32 " of %" PRIu32 " words wrong\n", queue, what, wrong, n);
    return wrong;
}

static uint32_t verify(struct job *j, int queue, uint32_t *want)
{
    const uint32_t words = BUFFER_SIZE / 4, image_words = IMAGE_W * IMAGE_H;
    uint32_t wrong = 0;
    for (uint32_t i = 0; i < words; ++i)
        want[i] = j->seed;
    wrong += compare("buffer fill", queue, j->fill.data, want, words);
    wrong += compare("buffer copy", queue, j->copy.data, j->src.data, words);
    wrong += compare("image copy", queue, j->back.data, j->src.data, image_words);
    for (uint32_t i = 0; i < DISPATCH_COUNT; ++i)
        want[i] = expected(i, j->seed);
    wrong += compare("dispatch", queue, j->out.data, want, DISPATCH_COUNT);
    return wrong;
}

// One round: a new device with *count* queues of *family*, the same job on every queue at once, then teardown.
static int run_round(uint32_t family, uint32_t count, uint32_t round)
{
    float priorities[64];
    for (uint32_t i = 0; i < count; ++i)
        priorities[i] = 1.0f;
    VkDeviceQueueCreateInfo queue_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family,
        .queueCount = count,
        .pQueuePriorities = priorities,
    };
    VkDeviceCreateInfo dev_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = &queue_info,
    };
    CHECK(vkCreateDevice(gpu, &dev_info, NULL, &dev));

    VkShaderModuleCreateInfo module_info = {
        .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
        .codeSize = sizeof(shader_code),
        .pCode = shader_code,
    };
    VkShaderModule module;
    CHECK(vkCreateShaderModule(dev, &module_info, NULL, &module));
    VkDescriptorSetLayoutBinding binding = {0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT,
                                            NULL};
    VkDescriptorSetLayoutCreateInfo set_info = {
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
        .bindingCount = 1,
        .pBindings = &binding,
    };
    VkDescriptorSetLayout set_layout;
    CHECK(vkCreateDescriptorSetLayout(dev, &set_info, NULL, &set_layout));
    VkPushConstantRange push_range = {VK_SHADER_STAGE_COMPUTE_BIT, 0, 8};
    VkPipelineLayoutCreateInfo layout_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .setLayoutCount = 1,
        .pSetLayouts = &set_layout,
        .pushConstantRangeCount = 1,
        .pPushConstantRanges = &push_range,
    };
    VkPipelineLayout layout;
    CHECK(vkCreatePipelineLayout(dev, &layout_info, NULL, &layout));
    VkComputePipelineCreateInfo pipe_info = {
        .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
        .stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, NULL, 0, VK_SHADER_STAGE_COMPUTE_BIT, module,
                  "main", NULL},
        .layout = layout,
    };
    VkPipeline pipeline;
    CHECK(vkCreateComputePipelines(dev, VK_NULL_HANDLE, 1, &pipe_info, NULL, &pipeline));

    VkDescriptorPoolSize pool_size = {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, count};
    VkDescriptorPoolCreateInfo dpool_info = {
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
        .maxSets = count,
        .poolSizeCount = 1,
        .pPoolSizes = &pool_size,
    };
    VkDescriptorPool dpool;
    CHECK(vkCreateDescriptorPool(dev, &dpool_info, NULL, &dpool));
    VkCommandPoolCreateInfo cpool_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = family,
    };
    VkCommandPool cpool;
    CHECK(vkCreateCommandPool(dev, &cpool_info, NULL, &cpool));

    struct job *jobs = calloc(count, sizeof(*jobs));
    uint32_t *want = malloc(BUFFER_SIZE > DISPATCH_COUNT * 4 ? BUFFER_SIZE : DISPATCH_COUNT * 4);
    if (!jobs || !want) {
        printf("FAIL: out of memory\n");
        exit(EXIT_VULKAN);
    }
    const VkBufferUsageFlags transfer = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    for (uint32_t q = 0; q < count; ++q) {
        struct job *j = &jobs[q];
        j->seed = 0x9e3779b9u * (round * 64 + q + 1);
        vkGetDeviceQueue(dev, family, q, &j->queue);
        j->src = make_buffer(transfer);
        j->fill = make_buffer(transfer);
        j->copy = make_buffer(transfer);
        j->back = make_buffer(transfer);
        j->out = make_buffer(VK_BUFFER_USAGE_STORAGE_BUFFER_BIT);
        for (uint32_t i = 0; i < BUFFER_SIZE / 4; ++i)
            j->src.data[i] = pattern(i, j->seed);

        VkImageCreateInfo image_info = {
            .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .imageType = VK_IMAGE_TYPE_2D,
            .format = VK_FORMAT_R8G8B8A8_UINT,
            .extent = {IMAGE_W, IMAGE_H, 1},
            .mipLevels = 1,
            .arrayLayers = 1,
            .samples = VK_SAMPLE_COUNT_1_BIT,
            .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        };
        CHECK(vkCreateImage(dev, &image_info, NULL, &j->image));
        VkMemoryRequirements req;
        vkGetImageMemoryRequirements(dev, j->image, &req);
        j->image_memory = allocate(req, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        CHECK(vkBindImageMemory(dev, j->image, j->image_memory, 0));

        VkDescriptorSetAllocateInfo set_alloc = {
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
            .descriptorPool = dpool,
            .descriptorSetCount = 1,
            .pSetLayouts = &set_layout,
        };
        CHECK(vkAllocateDescriptorSets(dev, &set_alloc, &j->set));
        VkDescriptorBufferInfo out_info = {j->out.buffer, 0, VK_WHOLE_SIZE};
        VkWriteDescriptorSet write = {
            .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
            .dstSet = j->set,
            .descriptorCount = 1,
            .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            .pBufferInfo = &out_info,
        };
        vkUpdateDescriptorSets(dev, 1, &write, 0, NULL);

        VkCommandBufferAllocateInfo cmd_alloc = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
            .commandPool = cpool,
            .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
            .commandBufferCount = 1,
        };
        CHECK(vkAllocateCommandBuffers(dev, &cmd_alloc, &j->cmd));
        VkFenceCreateInfo fence_info = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        CHECK(vkCreateFence(dev, &fence_info, NULL, &j->fence));
        record(j, pipeline, layout);
    }

    // Every queue gets its job before any is waited for, so they run side by side.
    for (uint32_t q = 0; q < count; ++q) {
        VkSubmitInfo submit = {
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .commandBufferCount = 1,
            .pCommandBuffers = &jobs[q].cmd,
        };
        CHECK(vkQueueSubmit(jobs[q].queue, 1, &submit, jobs[q].fence));
    }
    uint32_t wrong = 0;
    for (uint32_t q = 0; q < count; ++q) {
        VkResult r = vkWaitForFences(dev, 1, &jobs[q].fence, VK_TRUE, FENCE_TIMEOUT_NS);
        if (r == VK_TIMEOUT) {
            printf("FAIL: queue %" PRIu32 " did not finish within %llu s (round %" PRIu32 ")\n", q,
                   FENCE_TIMEOUT_NS / 1000000000ull, round);
            exit(EXIT_TIMEOUT);
        }
        CHECK(r);
        wrong += verify(&jobs[q], (int)q, want);
    }

    for (uint32_t q = 0; q < count; ++q) {
        struct job *j = &jobs[q];
        vkDestroyFence(dev, j->fence, NULL);
        vkDestroyImage(dev, j->image, NULL);
        vkFreeMemory(dev, j->image_memory, NULL);
        free_buffer(&j->src);
        free_buffer(&j->fill);
        free_buffer(&j->copy);
        free_buffer(&j->back);
        free_buffer(&j->out);
    }
    vkDestroyCommandPool(dev, cpool, NULL);
    vkDestroyDescriptorPool(dev, dpool, NULL);
    vkDestroyPipeline(dev, pipeline, NULL);
    vkDestroyPipelineLayout(dev, layout, NULL);
    vkDestroyDescriptorSetLayout(dev, set_layout, NULL);
    vkDestroyShaderModule(dev, module, NULL);
    vkDestroyDevice(dev, NULL);
    free(jobs);
    free(want);
    return wrong ? EXIT_DATA : 0;
}

int main(int argc, char **argv)
{
    uint32_t rounds = 10;
    int any_queue = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--rounds") && i + 1 < argc)
            rounds = (uint32_t)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--any-queue"))
            any_queue = 1;
        else {
            fprintf(stderr, "usage: %s [--rounds N] [--any-queue]\n", argv[0]);
            return EXIT_VULKAN;
        }
    }
    setvbuf(stdout, NULL, _IOLBF, 0);       // each line reaches the log before a possible hang

    VkApplicationInfo app = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "bc250-ace-test",
        .apiVersion = VK_API_VERSION_1_2,
    };
    VkInstanceCreateInfo inst_info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    VkInstance instance;
    CHECK(vkCreateInstance(&inst_info, NULL, &instance));

    uint32_t n = 8;
    VkPhysicalDevice gpus[8];
    VkResult r = vkEnumeratePhysicalDevices(instance, &n, gpus);
    if (r != VK_SUCCESS && r != VK_INCOMPLETE)
        CHECK(r);
    uint32_t family = UINT32_MAX, count = 0;
    for (uint32_t g = 0; g < n && family == UINT32_MAX; ++g) {
        uint32_t nf = 16;
        VkQueueFamilyProperties families[16];
        vkGetPhysicalDeviceQueueFamilyProperties(gpus[g], &nf, families);
        for (uint32_t f = 0; f < nf; ++f) {
            VkQueueFlags flags = families[f].queueFlags;
            if ((flags & VK_QUEUE_COMPUTE_BIT) && (any_queue || !(flags & VK_QUEUE_GRAPHICS_BIT))) {
                gpu = gpus[g];
                family = f;
                count = families[f].queueCount < 64 ? families[f].queueCount : 64;
                break;
            }
        }
    }
    if (family == UINT32_MAX) {
        printf("FAIL: no dedicated compute queue family: this driver does not open the ACE queues\n");
        return EXIT_NO_ACE;
    }
    VkPhysicalDeviceDriverProperties driver = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
    VkPhysicalDeviceProperties2 props = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &driver};
    vkGetPhysicalDeviceProperties2(gpu, &props);
    vkGetPhysicalDeviceMemoryProperties(gpu, &mem_props);
    printf("Device: %s, %s %s\n", props.properties.deviceName, driver.driverName, driver.driverInfo);
    printf("Queue family %" PRIu32 ": %" PRIu32 " queue(s), %" PRIu32 " round(s)\n", family, count, rounds);

    int failed = 0;
    for (uint32_t round = 1; round <= rounds; ++round) {
        int rc = run_round(family, count, round);
        printf("Round %" PRIu32 "/%" PRIu32 ": %s\n", round, rounds, rc ? "WRONG DATA" : "ok");
        failed |= rc;
    }
    vkDestroyInstance(instance, NULL);
    printf(failed ? "FAIL: wrong data on a compute queue\n" : "PASS\n");
    return failed ? EXIT_DATA : 0;
}
