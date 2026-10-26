// SPDX-License-Identifier: GPL-3.0-or-later
// bc250-mesh-test: checks that the driver draws with mesh shaders and draws the right pixels, while its compute
// queues work beside it.
//
//   bc250-mesh-test [--rounds N] [--compute-on-graphics]
//
// Each round makes a new Vulkan device, so the rounds also repeat the setup and teardown, and does two things at
// once:
//  * Draws: a 16 x 16 grid of coloured tiles (256 x 256 pixels), four ways one after the other on the graphics
//    queue: task and mesh shaders, a mesh shader alone with the largest meshlets the extension allows (which the
//    driver has to split on this chip), and both again from an indirect draw. Every pixel is compared with the colour
//    its tile must have. Task shaders run on the GPU's compute ring beside the graphics ring.
//  * Compute: when the driver offers a dedicated compute queue family (the ACE queues), every queue of it gets work
//    submitted before the draws: a copy from a buffer into an image and back (the driver's own copy shaders) and
//    dispatches whose last workgroup is a partial one. The results are compared word for word after the draws.
//    Without such a family only the draws are tested, and the output says so. --compute-on-graphics gives the
//    compute work to the graphics queue before the draws instead, for trying the test on a driver without one.
//
// Exit status: 0 passed, 1 wrong pixels or data, 2 Vulkan error, 3 no mesh and task shaders, 4 the GPU did not
// finish within the time limit (a GPU hang is likely; see the kernel log).
#include <vulkan/vulkan.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const uint32_t task_code[] =
#include "mesh-test.task.spv.inc"
;
static const uint32_t mesh_task_code[] =
#include "mesh-test-task.mesh.spv.inc"
;
static const uint32_t mesh_alone_code[] =
#include "mesh-test-alone.mesh.spv.inc"
;
static const uint32_t frag_code[] =
#include "mesh-test.frag.spv.inc"
;
static const uint32_t comp_code[] =
#include "mesh-test.comp.spv.inc"
;

#define SIZE 256u                       // pixels, both ways
#define TILES 16u                       // tiles per row and per column
#define TASK_GROUPS 4u                  // 4 task workgroups x 4 mesh workgroups x 1 row, or 4 mesh workgroups x 4 rows
#define COPY_W 1000u                    // the compute queues' image: not a multiple of 8, so the copy shaders'
#define COPY_H 777u                     // last workgroups are partial ones
#define DISPATCH_COUNT 1000003u         // not a multiple of 64
#define DISPATCHES 32u                  // the same dispatch again and again, to keep the queue busy during the draws
#define MAX_COMPUTE_QUEUES 8u
#define FENCE_TIMEOUT_NS (30ull * 1000 * 1000 * 1000)

#define EXIT_DATA 1
#define EXIT_VULKAN 2
#define EXIT_NO_MESH 3
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
    void *data;
};

// The work of one compute queue.
struct job {
    VkQueue queue;
    VkCommandBuffer cmd;
    VkFence fence;
    VkDescriptorSet set;
    struct buffer src, back, out;
    VkImage image;
    VkDeviceMemory image_memory;
    uint32_t seed;
};

// The four draws: with or without the task shader, direct or indirect.
static const struct draw {
    const char *name;
    int task, indirect;
} draws[] = {
    {"task + mesh", 1, 0},
    {"mesh alone, 256 vertices per workgroup", 0, 0},
    {"task + mesh, indirect", 1, 1},
    {"mesh alone, indirect", 0, 1},
};
#define DRAWS (sizeof(draws) / sizeof(draws[0]))

static VkPhysicalDevice gpu;
static VkDevice dev;
static VkPhysicalDeviceMemoryProperties mem_props;
static PFN_vkCmdDrawMeshTasksEXT draw_mesh_tasks;
static PFN_vkCmdDrawMeshTasksIndirectEXT draw_mesh_tasks_indirect;

// The colour of tile *id*, as the mesh shader computes it, packed as R8G8B8A8 in memory order.
static uint32_t tile_colour(uint32_t id, uint32_t seed, uint32_t pass)
{
    uint32_t r = (id + seed) & 255u;
    uint32_t g = (id * 3u + pass * 85u) & 255u;
    uint32_t b = (255u - id) ^ (seed >> 8 & 255u);
    return r | g << 8 | b << 16 | 255u << 24;
}

// The compute shader's value, computed on the CPU.
static uint32_t computed(uint32_t i, uint32_t seed)
{
    uint32_t v = i * 2654435769u ^ seed;
    for (int k = 0; k < 8; ++k) {
        v ^= v << 13;
        v ^= v >> 17;
        v ^= v << 5;
    }
    return v;
}

static uint32_t pattern(uint32_t i, uint32_t seed) { return (i * 2246822519u) ^ seed; }

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

static struct buffer make_buffer(VkDeviceSize size, VkBufferUsageFlags usage)
{
    struct buffer b;
    VkBufferCreateInfo info = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = size,
        .usage = usage,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
    };
    CHECK(vkCreateBuffer(dev, &info, NULL, &b.buffer));
    VkMemoryRequirements req;
    vkGetBufferMemoryRequirements(dev, b.buffer, &req);
    b.memory = allocate(req, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    CHECK(vkBindBufferMemory(dev, b.buffer, b.memory, 0));
    CHECK(vkMapMemory(dev, b.memory, 0, size, 0, &b.data));
    memset(b.data, 0, size);
    return b;
}

static void free_buffer(struct buffer *b)
{
    vkUnmapMemory(dev, b->memory);
    vkDestroyBuffer(dev, b->buffer, NULL);
    vkFreeMemory(dev, b->memory, NULL);
}

static VkImage make_image(uint32_t w, uint32_t h, VkFormat format, VkImageUsageFlags usage, VkDeviceMemory *memory)
{
    VkImageCreateInfo info = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        .imageType = VK_IMAGE_TYPE_2D,
        .format = format,
        .extent = {w, h, 1},
        .mipLevels = 1,
        .arrayLayers = 1,
        .samples = VK_SAMPLE_COUNT_1_BIT,
        .tiling = VK_IMAGE_TILING_OPTIMAL,
        .usage = usage,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
        .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
    };
    VkImage image;
    CHECK(vkCreateImage(dev, &info, NULL, &image));
    VkMemoryRequirements req;
    vkGetImageMemoryRequirements(dev, image, &req);
    *memory = allocate(req, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    CHECK(vkBindImageMemory(dev, image, *memory, 0));
    return image;
}

static VkShaderModule make_module(const uint32_t *code, size_t size)
{
    VkShaderModuleCreateInfo info = {
        .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
        .codeSize = size,
        .pCode = code,
    };
    VkShaderModule module;
    CHECK(vkCreateShaderModule(dev, &info, NULL, &module));
    return module;
}

static VkPipeline make_pipeline(VkPipelineLayout layout, VkShaderModule task, VkShaderModule mesh,
                                VkShaderModule frag)
{
    VkPipelineShaderStageCreateInfo stages[3];
    uint32_t n = 0;
    if (task)
        stages[n++] = (VkPipelineShaderStageCreateInfo){VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, NULL, 0,
                                                        VK_SHADER_STAGE_TASK_BIT_EXT, task, "main", NULL};
    stages[n++] = (VkPipelineShaderStageCreateInfo){VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, NULL, 0,
                                                    VK_SHADER_STAGE_MESH_BIT_EXT, mesh, "main", NULL};
    stages[n++] = (VkPipelineShaderStageCreateInfo){VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, NULL, 0,
                                                    VK_SHADER_STAGE_FRAGMENT_BIT, frag, "main", NULL};
    VkPipelineViewportStateCreateInfo viewport = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
        .viewportCount = 1,
        .scissorCount = 1,
    };
    VkPipelineRasterizationStateCreateInfo raster = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
        .polygonMode = VK_POLYGON_MODE_FILL,
        .cullMode = VK_CULL_MODE_NONE,
        .frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE,
        .lineWidth = 1.0f,
    };
    VkPipelineMultisampleStateCreateInfo multisample = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
        .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT,
    };
    VkPipelineColorBlendAttachmentState attachment = {
        .colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT |
                          VK_COLOR_COMPONENT_A_BIT,
    };
    VkPipelineColorBlendStateCreateInfo blend = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
        .attachmentCount = 1,
        .pAttachments = &attachment,
    };
    VkDynamicState dynamic_states[] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
    VkPipelineDynamicStateCreateInfo dynamic = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
        .dynamicStateCount = 2,
        .pDynamicStates = dynamic_states,
    };
    VkFormat format = VK_FORMAT_R8G8B8A8_UNORM;
    VkPipelineRenderingCreateInfo rendering = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO,
        .colorAttachmentCount = 1,
        .pColorAttachmentFormats = &format,
    };
    VkGraphicsPipelineCreateInfo info = {
        .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
        .pNext = &rendering,
        .stageCount = n,
        .pStages = stages,
        .pViewportState = &viewport,
        .pRasterizationState = &raster,
        .pMultisampleState = &multisample,
        .pColorBlendState = &blend,
        .pDynamicState = &dynamic,
        .layout = layout,
    };
    VkPipeline pipeline;
    CHECK(vkCreateGraphicsPipelines(dev, VK_NULL_HANDLE, 1, &info, NULL, &pipeline));
    return pipeline;
}

static void image_barrier(VkCommandBuffer cmd, VkImage image, VkImageLayout from, VkImageLayout to,
                          VkPipelineStageFlags src_stage, VkAccessFlags src_access, VkPipelineStageFlags dst_stage,
                          VkAccessFlags dst_access)
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
    vkCmdPipelineBarrier(cmd, src_stage, dst_stage, 0, 0, NULL, 0, NULL, 1, &barrier);
}

static void begin(VkCommandBuffer cmd)
{
    VkCommandBufferBeginInfo info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
    };
    CHECK(vkBeginCommandBuffer(cmd, &info));
}

static void to_host(VkCommandBuffer cmd, VkPipelineStageFlags stages, VkAccessFlags access)
{
    VkMemoryBarrier barrier = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .srcAccessMask = access,
        .dstAccessMask = VK_ACCESS_HOST_READ_BIT,
    };
    vkCmdPipelineBarrier(cmd, stages, VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &barrier, 0, NULL, 0, NULL);
}

// Clear, draw and copy the pixels to *readback*.
static void record_draw(VkCommandBuffer cmd, const struct draw *d, VkPipeline pipeline, VkPipelineLayout layout,
                        VkImage image, VkImageView view, VkBuffer indirect, VkBuffer readback, const uint32_t push[2])
{
    begin(cmd);
    image_barrier(cmd, image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                  VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, 0, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                  VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
    VkRenderingAttachmentInfo colour = {
        .sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO,
        .imageView = view,
        .imageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
        .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
        .clearValue = {.color = {.float32 = {0, 0, 0, 0}}},
    };
    VkRenderingInfo rendering = {
        .sType = VK_STRUCTURE_TYPE_RENDERING_INFO,
        .renderArea = {{0, 0}, {SIZE, SIZE}},
        .layerCount = 1,
        .colorAttachmentCount = 1,
        .pColorAttachments = &colour,
    };
    vkCmdBeginRendering(cmd, &rendering);
    VkViewport viewport = {0, 0, SIZE, SIZE, 0, 1};
    VkRect2D scissor = {{0, 0}, {SIZE, SIZE}};
    vkCmdSetViewport(cmd, 0, 1, &viewport);
    vkCmdSetScissor(cmd, 0, 1, &scissor);
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
    vkCmdPushConstants(cmd, layout, VK_SHADER_STAGE_MESH_BIT_EXT, 0, 8, push);
    if (d->indirect)
        draw_mesh_tasks_indirect(cmd, indirect, 0, 1, sizeof(VkDrawMeshTasksIndirectCommandEXT));
    else
        draw_mesh_tasks(cmd, TASK_GROUPS, 1, 1);
    vkCmdEndRendering(cmd);

    image_barrier(cmd, image, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                  VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
                  VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_READ_BIT);
    VkBufferImageCopy region = {
        .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
        .imageExtent = {SIZE, SIZE, 1},
    };
    vkCmdCopyImageToBuffer(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, readback, 1, &region);
    to_host(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT);
    CHECK(vkEndCommandBuffer(cmd));
}

// A compute queue's work: the image round trip, then the dispatches.
static void record_compute(struct job *j, VkPipeline pipeline, VkPipelineLayout layout)
{
    begin(j->cmd);
    VkBufferImageCopy region = {
        .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
        .imageExtent = {COPY_W, COPY_H, 1},
    };
    image_barrier(j->cmd, j->image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                  VK_PIPELINE_STAGE_TRANSFER_BIT, 0, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT);
    vkCmdCopyBufferToImage(j->cmd, j->src.buffer, j->image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
    image_barrier(j->cmd, j->image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                  VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                  VK_ACCESS_TRANSFER_READ_BIT);
    vkCmdCopyImageToBuffer(j->cmd, j->image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, j->back.buffer, 1, &region);

    uint32_t push[2] = {DISPATCH_COUNT, j->seed};
    vkCmdBindPipeline(j->cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
    vkCmdBindDescriptorSets(j->cmd, VK_PIPELINE_BIND_POINT_COMPUTE, layout, 0, 1, &j->set, 0, NULL);
    vkCmdPushConstants(j->cmd, layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(push), push);
    for (uint32_t k = 0; k < DISPATCHES; ++k)       // every dispatch writes the same values
        vkCmdDispatch(j->cmd, (DISPATCH_COUNT + 63) / 64, 1, 1);
    to_host(j->cmd, VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
            VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_SHADER_WRITE_BIT);
    CHECK(vkEndCommandBuffer(j->cmd));
}

// Compares every pixel with its tile's colour; prints the first wrong one. Returns the number of wrong pixels.
static uint32_t verify_pixels(const char *what, const uint32_t *pixels, uint32_t seed, uint32_t pass)
{
    uint32_t wrong = 0;
    for (uint32_t y = 0; y < SIZE; ++y) {
        for (uint32_t x = 0; x < SIZE; ++x) {
            uint32_t got = pixels[y * SIZE + x];
            uint32_t want = tile_colour((y / (SIZE / TILES)) * TILES + x / (SIZE / TILES), seed, pass);
            if (got == want)
                continue;
            if (!wrong++)
                printf("  %s: pixel (%" PRIu32 ", %" PRIu32 ") is 0x%08" PRIx32 ", expected 0x%08" PRIx32 "%s\n",
                       what, x, y, got, want, got >> 24 ? "" : " (not drawn)");
        }
    }
    if (wrong)
        printf("  %s: %" PRIu32 " of %u pixels wrong\n", what, wrong, SIZE * SIZE);
    return wrong;
}

// Compares a compute queue's results word for word; prints the first wrong one. Returns the number of wrong words.
static uint32_t verify_compute(const struct job *j, uint32_t queue)
{
    const uint32_t *back = j->back.data, *src = j->src.data, *out = j->out.data;
    uint32_t wrong_copy = 0, wrong_dispatch = 0;
    for (uint32_t i = 0; i < COPY_W * COPY_H; ++i)
        if (back[i] != src[i] && !wrong_copy++)
            printf("  compute queue %" PRIu32 ", image copy: word %" PRIu32 " is 0x%08" PRIx32 ", expected 0x%08" PRIx32
                   "\n", queue, i, back[i], src[i]);
    for (uint32_t i = 0; i < DISPATCH_COUNT; ++i)
        if (out[i] != computed(i, j->seed) && !wrong_dispatch++)
            printf("  compute queue %" PRIu32 ", dispatch: word %" PRIu32 " is 0x%08" PRIx32 ", expected 0x%08" PRIx32
                   "\n", queue, i, out[i], computed(i, j->seed));
    if (wrong_copy)
        printf("  compute queue %" PRIu32 ", image copy: %" PRIu32 " of %u words wrong\n", queue, wrong_copy,
               COPY_W * COPY_H);
    if (wrong_dispatch)
        printf("  compute queue %" PRIu32 ", dispatch: %" PRIu32 " of %u words wrong\n", queue, wrong_dispatch,
               DISPATCH_COUNT);
    return wrong_copy + wrong_dispatch;
}

static void wait_for(VkFence fence, const char *what, uint32_t round)
{
    VkResult r = vkWaitForFences(dev, 1, &fence, VK_TRUE, FENCE_TIMEOUT_NS);
    if (r == VK_TIMEOUT) {
        printf("FAIL: %s did not finish within %llu s (round %" PRIu32 ")\n", what, FENCE_TIMEOUT_NS / 1000000000ull,
               round);
        exit(EXIT_TIMEOUT);
    }
    CHECK(r);
}

// One round: a new device; the compute queues' work submitted, the four draws one after the other on the graphics
// queue meanwhile, then the compute results; then teardown.
static int run_round(uint32_t family, uint32_t compute_family, uint32_t compute_count, uint32_t round)
{
    float priorities[MAX_COMPUTE_QUEUES];
    for (uint32_t i = 0; i < MAX_COMPUTE_QUEUES; ++i)
        priorities[i] = 1.0f;
    VkDeviceQueueCreateInfo queue_infos[2] = {
        {
            .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
            .queueFamilyIndex = family,
            .queueCount = 1,
            .pQueuePriorities = priorities,
        },
        {
            .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
            .queueFamilyIndex = compute_family,
            .queueCount = compute_count,
            .pQueuePriorities = priorities,
        },
    };
    VkPhysicalDeviceMeshShaderFeaturesEXT mesh_features = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MESH_SHADER_FEATURES_EXT,
        .taskShader = VK_TRUE,
        .meshShader = VK_TRUE,
    };
    VkPhysicalDeviceVulkan13Features features13 = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
        .pNext = &mesh_features,
        .dynamicRendering = VK_TRUE,
    };
    const char *extensions[] = {VK_EXT_MESH_SHADER_EXTENSION_NAME};
    VkDeviceCreateInfo dev_info = {
        .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .pNext = &features13,
        .queueCreateInfoCount = compute_count && compute_family != family ? 2 : 1,
        .pQueueCreateInfos = queue_infos,
        .enabledExtensionCount = 1,
        .ppEnabledExtensionNames = extensions,
    };
    CHECK(vkCreateDevice(gpu, &dev_info, NULL, &dev));
    draw_mesh_tasks = (PFN_vkCmdDrawMeshTasksEXT)vkGetDeviceProcAddr(dev, "vkCmdDrawMeshTasksEXT");
    draw_mesh_tasks_indirect =
        (PFN_vkCmdDrawMeshTasksIndirectEXT)vkGetDeviceProcAddr(dev, "vkCmdDrawMeshTasksIndirectEXT");
    if (!draw_mesh_tasks || !draw_mesh_tasks_indirect) {
        printf("FAIL: the driver has no vkCmdDrawMeshTasksEXT\n");
        exit(EXIT_NO_MESH);
    }
    VkQueue queue;
    vkGetDeviceQueue(dev, family, 0, &queue);

    // The draws.
    VkShaderModule task = make_module(task_code, sizeof(task_code));
    VkShaderModule mesh_task = make_module(mesh_task_code, sizeof(mesh_task_code));
    VkShaderModule mesh_alone = make_module(mesh_alone_code, sizeof(mesh_alone_code));
    VkShaderModule frag = make_module(frag_code, sizeof(frag_code));
    VkPushConstantRange draw_push = {VK_SHADER_STAGE_MESH_BIT_EXT, 0, 8};
    VkPipelineLayoutCreateInfo draw_layout_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .pushConstantRangeCount = 1,
        .pPushConstantRanges = &draw_push,
    };
    VkPipelineLayout draw_layout;
    CHECK(vkCreatePipelineLayout(dev, &draw_layout_info, NULL, &draw_layout));
    VkPipeline with_task = make_pipeline(draw_layout, task, mesh_task, frag);
    VkPipeline alone = make_pipeline(draw_layout, VK_NULL_HANDLE, mesh_alone, frag);
    VkDeviceMemory image_memory;
    VkImage image = make_image(SIZE, SIZE, VK_FORMAT_R8G8B8A8_UNORM,
                               VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT, &image_memory);
    VkImageViewCreateInfo view_info = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
        .image = image,
        .viewType = VK_IMAGE_VIEW_TYPE_2D,
        .format = VK_FORMAT_R8G8B8A8_UNORM,
        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1},
    };
    VkImageView view;
    CHECK(vkCreateImageView(dev, &view_info, NULL, &view));
    struct buffer indirect = make_buffer(sizeof(VkDrawMeshTasksIndirectCommandEXT),
                                         VK_BUFFER_USAGE_INDIRECT_BUFFER_BIT);
    *(VkDrawMeshTasksIndirectCommandEXT *)indirect.data = (VkDrawMeshTasksIndirectCommandEXT){TASK_GROUPS, 1, 1};
    struct buffer readback = make_buffer(SIZE * SIZE * 4, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
    VkCommandPoolCreateInfo pool_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
        .queueFamilyIndex = family,
    };
    VkCommandPool pool;
    CHECK(vkCreateCommandPool(dev, &pool_info, NULL, &pool));
    VkCommandBufferAllocateInfo cmd_alloc = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool,
        .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    VkCommandBuffer cmd;
    CHECK(vkAllocateCommandBuffers(dev, &cmd_alloc, &cmd));
    VkFenceCreateInfo fence_info = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence;
    CHECK(vkCreateFence(dev, &fence_info, NULL, &fence));

    // The compute queues' work.
    VkShaderModule comp = make_module(comp_code, sizeof(comp_code));
    VkDescriptorSetLayoutBinding binding = {0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT,
                                            NULL};
    VkDescriptorSetLayoutCreateInfo set_info = {
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
        .bindingCount = 1,
        .pBindings = &binding,
    };
    VkDescriptorSetLayout set_layout;
    CHECK(vkCreateDescriptorSetLayout(dev, &set_info, NULL, &set_layout));
    VkPushConstantRange comp_push = {VK_SHADER_STAGE_COMPUTE_BIT, 0, 8};
    VkPipelineLayoutCreateInfo comp_layout_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .setLayoutCount = 1,
        .pSetLayouts = &set_layout,
        .pushConstantRangeCount = 1,
        .pPushConstantRanges = &comp_push,
    };
    VkPipelineLayout comp_layout;
    CHECK(vkCreatePipelineLayout(dev, &comp_layout_info, NULL, &comp_layout));
    VkComputePipelineCreateInfo comp_info = {
        .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
        .stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, NULL, 0, VK_SHADER_STAGE_COMPUTE_BIT, comp,
                  "main", NULL},
        .layout = comp_layout,
    };
    VkPipeline comp_pipeline;
    CHECK(vkCreateComputePipelines(dev, VK_NULL_HANDLE, 1, &comp_info, NULL, &comp_pipeline));
    VkDescriptorPoolSize pool_size = {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, MAX_COMPUTE_QUEUES};
    VkDescriptorPoolCreateInfo dpool_info = {
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
        .maxSets = MAX_COMPUTE_QUEUES,
        .poolSizeCount = 1,
        .pPoolSizes = &pool_size,
    };
    VkDescriptorPool dpool;
    CHECK(vkCreateDescriptorPool(dev, &dpool_info, NULL, &dpool));
    VkCommandPool comp_pool = VK_NULL_HANDLE;
    if (compute_count) {
        VkCommandPoolCreateInfo comp_pool_info = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
            .queueFamilyIndex = compute_family,
        };
        CHECK(vkCreateCommandPool(dev, &comp_pool_info, NULL, &comp_pool));
    }
    struct job jobs[MAX_COMPUTE_QUEUES];
    const VkBufferUsageFlags transfer = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    for (uint32_t q = 0; q < compute_count; ++q) {
        struct job *j = &jobs[q];
        j->seed = 0x85ebca6bu * (round * 16 + q + 1);
        vkGetDeviceQueue(dev, compute_family, q, &j->queue);
        j->src = make_buffer(COPY_W * COPY_H * 4, transfer);
        j->back = make_buffer(COPY_W * COPY_H * 4, transfer);
        j->out = make_buffer(DISPATCH_COUNT * 4, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT);
        uint32_t *src = j->src.data;
        for (uint32_t i = 0; i < COPY_W * COPY_H; ++i)
            src[i] = pattern(i, j->seed);
        j->image = make_image(COPY_W, COPY_H, VK_FORMAT_R8G8B8A8_UINT,
                              VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT, &j->image_memory);
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
        VkCommandBufferAllocateInfo comp_alloc = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
            .commandPool = comp_pool,
            .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
            .commandBufferCount = 1,
        };
        CHECK(vkAllocateCommandBuffers(dev, &comp_alloc, &j->cmd));
        CHECK(vkCreateFence(dev, &fence_info, NULL, &j->fence));
        record_compute(j, comp_pipeline, comp_layout);
    }

    // Every compute queue gets its work before the first draw, so they run beside the draws.
    for (uint32_t q = 0; q < compute_count; ++q) {
        VkSubmitInfo submit = {
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .commandBufferCount = 1,
            .pCommandBuffers = &jobs[q].cmd,
        };
        CHECK(vkQueueSubmit(jobs[q].queue, 1, &submit, jobs[q].fence));
    }
    uint32_t wrong = 0;
    for (uint32_t pass = 0; pass < DRAWS; ++pass) {
        const struct draw *d = &draws[pass];
        uint32_t push[2] = {0x9e3779b9u * (round * 8 + pass + 1), pass};
        memset(readback.data, 0, SIZE * SIZE * 4);
        record_draw(cmd, d, d->task ? with_task : alone, draw_layout, image, view, indirect.buffer, readback.buffer,
                    push);
        VkSubmitInfo submit = {
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .commandBufferCount = 1,
            .pCommandBuffers = &cmd,
        };
        CHECK(vkQueueSubmit(queue, 1, &submit, fence));
        wait_for(fence, d->name, round);
        CHECK(vkResetFences(dev, 1, &fence));
        CHECK(vkResetCommandBuffer(cmd, 0));
        wrong += verify_pixels(d->name, readback.data, push[0], push[1]);
    }
    for (uint32_t q = 0; q < compute_count; ++q) {
        wait_for(jobs[q].fence, "a compute queue", round);
        wrong += verify_compute(&jobs[q], q);
    }

    for (uint32_t q = 0; q < compute_count; ++q) {
        struct job *j = &jobs[q];
        vkDestroyFence(dev, j->fence, NULL);
        vkDestroyImage(dev, j->image, NULL);
        vkFreeMemory(dev, j->image_memory, NULL);
        free_buffer(&j->src);
        free_buffer(&j->back);
        free_buffer(&j->out);
    }
    if (comp_pool)
        vkDestroyCommandPool(dev, comp_pool, NULL);
    vkDestroyDescriptorPool(dev, dpool, NULL);
    vkDestroyPipeline(dev, comp_pipeline, NULL);
    vkDestroyPipelineLayout(dev, comp_layout, NULL);
    vkDestroyDescriptorSetLayout(dev, set_layout, NULL);
    vkDestroyShaderModule(dev, comp, NULL);
    vkDestroyFence(dev, fence, NULL);
    vkDestroyCommandPool(dev, pool, NULL);
    free_buffer(&indirect);
    free_buffer(&readback);
    vkDestroyImageView(dev, view, NULL);
    vkDestroyImage(dev, image, NULL);
    vkFreeMemory(dev, image_memory, NULL);
    vkDestroyPipeline(dev, with_task, NULL);
    vkDestroyPipeline(dev, alone, NULL);
    vkDestroyPipelineLayout(dev, draw_layout, NULL);
    vkDestroyShaderModule(dev, task, NULL);
    vkDestroyShaderModule(dev, mesh_task, NULL);
    vkDestroyShaderModule(dev, mesh_alone, NULL);
    vkDestroyShaderModule(dev, frag, NULL);
    vkDestroyDevice(dev, NULL);
    return wrong ? EXIT_DATA : 0;
}

// True when *g* offers VK_EXT_mesh_shader with task and mesh shaders, and dynamic rendering.
static int has_mesh_shaders(VkPhysicalDevice g)
{
    uint32_t n = 0;
    if (vkEnumerateDeviceExtensionProperties(g, NULL, &n, NULL) != VK_SUCCESS || !n)
        return 0;
    VkExtensionProperties *extensions = calloc(n, sizeof(*extensions));
    int found = 0;
    if (extensions && vkEnumerateDeviceExtensionProperties(g, NULL, &n, extensions) == VK_SUCCESS)
        for (uint32_t i = 0; i < n && !found; ++i)
            found = !strcmp(extensions[i].extensionName, VK_EXT_MESH_SHADER_EXTENSION_NAME);
    free(extensions);
    if (!found)
        return 0;
    VkPhysicalDeviceMeshShaderFeaturesEXT mesh = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MESH_SHADER_FEATURES_EXT};
    VkPhysicalDeviceVulkan13Features features13 = {
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
        .pNext = &mesh,
    };
    VkPhysicalDeviceFeatures2 features = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &features13};
    vkGetPhysicalDeviceFeatures2(g, &features);
    return mesh.taskShader && mesh.meshShader && features13.dynamicRendering;
}

int main(int argc, char **argv)
{
    uint32_t rounds = 10;
    int compute_on_graphics = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--rounds") && i + 1 < argc)
            rounds = (uint32_t)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--compute-on-graphics"))
            compute_on_graphics = 1;
        else {
            fprintf(stderr, "usage: %s [--rounds N] [--compute-on-graphics]\n", argv[0]);
            return EXIT_VULKAN;
        }
    }
    setvbuf(stdout, NULL, _IOLBF, 0);       // each line reaches the log before a possible hang

    VkApplicationInfo app = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "bc250-mesh-test",
        .apiVersion = VK_API_VERSION_1_3,
    };
    VkInstanceCreateInfo inst_info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    VkInstance instance;
    CHECK(vkCreateInstance(&inst_info, NULL, &instance));

    uint32_t n = 8;
    VkPhysicalDevice gpus[8];
    VkResult r = vkEnumeratePhysicalDevices(instance, &n, gpus);
    if (r != VK_SUCCESS && r != VK_INCOMPLETE)
        CHECK(r);
    uint32_t family = UINT32_MAX, compute_family = UINT32_MAX, compute_count = 0;
    for (uint32_t g = 0; g < n && family == UINT32_MAX; ++g) {
        VkPhysicalDeviceProperties p;
        vkGetPhysicalDeviceProperties(gpus[g], &p);
        if (p.apiVersion < VK_API_VERSION_1_3 || !has_mesh_shaders(gpus[g]))
            continue;
        uint32_t nf = 16;
        VkQueueFamilyProperties families[16];
        vkGetPhysicalDeviceQueueFamilyProperties(gpus[g], &nf, families);
        for (uint32_t f = 0; f < nf; ++f) {
            VkQueueFlags flags = families[f].queueFlags;
            if ((flags & VK_QUEUE_GRAPHICS_BIT) && family == UINT32_MAX) {
                gpu = gpus[g];
                family = f;
            } else if ((flags & VK_QUEUE_COMPUTE_BIT) && !(flags & VK_QUEUE_GRAPHICS_BIT) &&
                       compute_family == UINT32_MAX) {
                compute_family = f;
                compute_count = families[f].queueCount < MAX_COMPUTE_QUEUES ? families[f].queueCount
                                                                           : MAX_COMPUTE_QUEUES;
            }
        }
        if (family == UINT32_MAX)
            compute_family = UINT32_MAX, compute_count = 0;
    }
    if (compute_on_graphics && family != UINT32_MAX) {
        compute_family = family;
        compute_count = 1;
    }
    if (family == UINT32_MAX) {
        printf("FAIL: no device with mesh and task shaders: this driver does not offer them\n");
        return EXIT_NO_MESH;
    }
    VkPhysicalDeviceDriverProperties driver = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
    VkPhysicalDeviceProperties2 props = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &driver};
    vkGetPhysicalDeviceProperties2(gpu, &props);
    vkGetPhysicalDeviceMemoryProperties(gpu, &mem_props);
    printf("Device: %s, %s %s\n", props.properties.deviceName, driver.driverName, driver.driverInfo);
    printf("Graphics queue family %" PRIu32 ": %zu draws, %" PRIu32 " round(s)\n", family, DRAWS, rounds);
    if (compute_family == family)
        printf("Compute work on the graphics queue, before the draws\n");
    else if (compute_count)
        printf("Compute queue family %" PRIu32 ": %" PRIu32 " queue(s) working beside the draws\n", compute_family,
               compute_count);
    else
        printf("No dedicated compute queue family (the driver keeps the ACE queues closed): only the draws are "
               "tested\n");

    int failed = 0;
    for (uint32_t round = 1; round <= rounds; ++round) {
        int rc = run_round(family, compute_family, compute_count, round);
        printf("Round %" PRIu32 "/%" PRIu32 ": %s\n", round, rounds, rc ? "WRONG DATA" : "ok");
        failed |= rc;
    }
    vkDestroyInstance(instance, NULL);
    printf(failed ? "FAIL: wrong pixels or data\n" : "PASS\n");
    return failed ? EXIT_DATA : 0;
}
