// SPDX-License-Identifier: AGPL-3.0-only
// The video decoder over FFmpeg's libavcodec (as the reference's ffmpegdecoder.c uses it): H.264 or HEVC, with VA-API
// when the board's driver opens, else in software; and the Opus decoder for the sound. A small C interface, so the
// Rust side (decoder.rs) needs neither bindgen nor FFmpeg's struct layouts.

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <libavcodec/avcodec.h>
#include <libavutil/channel_layout.h>
#include <libavutil/common.h>
#include <libavutil/hwcontext.h>
#include <libavutil/imgutils.h>
#include <libavutil/log.h>
#include <libavutil/pixdesc.h>

struct bc_decoder {
    AVCodecContext *ctx;
    AVBufferRef *hw_device;
    AVPacket *packet;
    AVFrame *frame;         // the last frame received
    AVFrame *next;          // receiving into this keeps the last frame when there is none
    AVFrame *transferred;   // its picture in memory, for a VA-API frame
    int has_frame;
};

struct bc_frame {
    int width;
    int height;
    int hw;                 // 1: the picture is on the GPU (VA-API)
};

void bc_decoder_free(struct bc_decoder *d)
{
    if(!d)
        return;
    av_frame_free(&d->transferred);
    av_frame_free(&d->frame);
    av_frame_free(&d->next);
    av_packet_free(&d->packet);
    avcodec_free_context(&d->ctx);
    av_buffer_unref(&d->hw_device);
    av_free(d);
}

const char *bc_decoder_ffmpeg_version(void)
{
    return av_version_info();
}

void bc_decoder_error(int code, char *buf, size_t size)
{
    av_strerror(code, buf, size);
}

// hevc: 0 for H.264. hw: try VA-API; *hw_error gets its error when that fails (the decoder then runs in software).
// low_delay: FFmpeg's low-delay mode (no frames held back for reordering; the stream's settings, low latency).
int bc_decoder_new(int hevc, int hw, int low_delay, struct bc_decoder **out, int *hw_error)
{
    *out = NULL;
    *hw_error = 0;
    av_log_set_level(AV_LOG_FATAL);     // errors come back as return codes; FFmpeg's log would go to stderr
    const AVCodec *codec = avcodec_find_decoder(hevc ? AV_CODEC_ID_HEVC : AV_CODEC_ID_H264);
    if(!codec)
        return AVERROR_DECODER_NOT_FOUND;
    struct bc_decoder *d = av_mallocz(sizeof(*d));
    if(!d)
        return AVERROR(ENOMEM);
    d->ctx = avcodec_alloc_context3(codec);
    d->packet = av_packet_alloc();
    d->frame = av_frame_alloc();
    d->next = av_frame_alloc();
    d->transferred = av_frame_alloc();
    if(!d->ctx || !d->packet || !d->frame || !d->next || !d->transferred)
    {
        bc_decoder_free(d);
        return AVERROR(ENOMEM);
    }
    if(hw)
    {
        int r = av_hwdevice_ctx_create(&d->hw_device, AV_HWDEVICE_TYPE_VAAPI, NULL, NULL, 0);
        if(r < 0)
            *hw_error = r;
        else
            d->ctx->hw_device_ctx = av_buffer_ref(d->hw_device);
    }
    if(low_delay)
        d->ctx->flags |= AV_CODEC_FLAG_LOW_DELAY;
    int r = avcodec_open2(d->ctx, codec, NULL);
    if(r < 0)
    {
        bc_decoder_free(d);
        return r;
    }
    *out = d;
    return 0;
}

int bc_decoder_hw(struct bc_decoder *d)
{
    return d->hw_device != NULL;
}

// One sample (the stream's header, or a frame). AVERROR(EAGAIN): receive the frames first.
int bc_decoder_send(struct bc_decoder *d, const uint8_t *data, size_t size)
{
    if(size > INT32_MAX - AV_INPUT_BUFFER_PADDING_SIZE)
        return AVERROR(EINVAL);
    int r = av_new_packet(d->packet, (int)size);       // with FFmpeg's zeroed padding after the data
    if(r < 0)
        return r;
    memcpy(d->packet->data, data, size);
    r = avcodec_send_packet(d->ctx, d->packet);
    av_packet_unref(d->packet);
    return r;
}

// 1 and *info: a frame; 0: none ready; < 0: an error.
int bc_decoder_receive(struct bc_decoder *d, struct bc_frame *info)
{
    int r = avcodec_receive_frame(d->ctx, d->next);
    if(r == AVERROR(EAGAIN) || r == AVERROR_EOF)
        return 0;
    if(r < 0)
        return r;
    av_frame_unref(d->frame);
    av_frame_move_ref(d->frame, d->next);
    d->has_frame = 1;
    info->width = d->frame->width;
    info->height = d->frame->height;
    info->hw = d->frame->format == AV_PIX_FMT_VAAPI;
    return 1;
}

static const AVFrame *picture(struct bc_decoder *d, int *r)
{
    *r = 0;
    if(!d->has_frame)
    {
        *r = AVERROR(EINVAL);
        return NULL;
    }
    if(d->frame->format != AV_PIX_FMT_VAAPI)
        return d->frame;
    av_frame_unref(d->transferred);
    *r = av_hwframe_transfer_data(d->transferred, d->frame, 0);
    return *r < 0 ? NULL : d->transferred;
}

// The last frame's picture: its pixel format's name (yuv420p in software, nv12 from VA-API) and size in bytes,
// planes one after another without padding; its colour matrix (FFmpeg's AVColorSpace: 1 BT.709, 5 and 6 BT.601,
// 9 BT.2020, 2 unspecified) and whether it uses the full range of values. bc_decoder_image_copy then copies it.
int bc_decoder_image(struct bc_decoder *d, char *format, size_t format_size, size_t *size, int *colorspace,
                     int *full_range)
{
    int r;
    const AVFrame *f = picture(d, &r);
    if(!f)
        return r;
    *colorspace = d->frame->colorspace;
    *full_range = d->frame->color_range == AVCOL_RANGE_JPEG;
    const char *name = av_get_pix_fmt_name(f->format);
    snprintf(format, format_size, "%s", name ? name : "?");
    r = av_image_get_buffer_size(f->format, f->width, f->height, 1);
    if(r < 0)
        return r;
    *size = (size_t)r;
    return 0;
}

int bc_decoder_image_copy(struct bc_decoder *d, uint8_t *buf, size_t size)
{
    const AVFrame *f = d->frame->format == AV_PIX_FMT_VAAPI ? d->transferred : d->frame;
    if(!d->has_frame || size > INT32_MAX)
        return AVERROR(EINVAL);
    return av_image_copy_to_buffer(buf, (int)size, (const uint8_t * const *)f->data, f->linesize, f->format,
                                   f->width, f->height, 1);
}

// --- Sound: Opus (the reference uses libopus; FFmpeg's own decoder here) ------------------------------------------

// An Opus decoder for raw frames of rate and channels as the stream's audio header gives them.
int bc_audio_new(int rate, int channels, struct bc_decoder **out)
{
    *out = NULL;
    av_log_set_level(AV_LOG_FATAL);
    const AVCodec *codec = avcodec_find_decoder(AV_CODEC_ID_OPUS);
    if(!codec)
        return AVERROR_DECODER_NOT_FOUND;
    struct bc_decoder *d = av_mallocz(sizeof(*d));
    if(!d)
        return AVERROR(ENOMEM);
    d->ctx = avcodec_alloc_context3(codec);
    d->packet = av_packet_alloc();
    d->frame = av_frame_alloc();
    if(!d->ctx || !d->packet || !d->frame)
    {
        bc_decoder_free(d);
        return AVERROR(ENOMEM);
    }
    d->ctx->sample_rate = rate;
    av_channel_layout_default(&d->ctx->ch_layout, channels);
    int r = avcodec_open2(d->ctx, codec, NULL);
    if(r < 0)
    {
        bc_decoder_free(d);
        return r;
    }
    *out = d;
    return 0;
}

static int16_t to_s16(float sample)
{
    return av_clip_int16(lrintf(sample * 32768.0f));
}

// One Opus frame into out, 16-bit samples interleaved: at most capacity samples per channel; *samples gets how many
// per channel it wrote.
int bc_audio_decode(struct bc_decoder *d, const uint8_t *data, size_t size, int16_t *out, size_t capacity,
                    int *samples)
{
    *samples = 0;
    if(size == 0 || size > INT32_MAX - AV_INPUT_BUFFER_PADDING_SIZE)
        return AVERROR(EINVAL);
    int r = av_new_packet(d->packet, (int)size);
    if(r < 0)
        return r;
    memcpy(d->packet->data, data, size);
    r = avcodec_send_packet(d->ctx, d->packet);
    av_packet_unref(d->packet);
    if(r < 0)
        return r;
    int channels = d->ctx->ch_layout.nb_channels;
    while((r = avcodec_receive_frame(d->ctx, d->frame)) >= 0)
    {
        AVFrame *f = d->frame;
        int n = f->nb_samples;
        if((size_t)(*samples + n) > capacity)
            n = (int)(capacity - (size_t)*samples);
        for(int i = 0; i < n; i++)
            for(int c = 0; c < channels; c++)
            {
                float sample;
                if(f->format == AV_SAMPLE_FMT_FLTP)
                    sample = ((const float *)f->extended_data[c])[i];
                else if(f->format == AV_SAMPLE_FMT_FLT)
                    sample = ((const float *)f->extended_data[0])[i * channels + c];
                else
                {
                    av_frame_unref(f);
                    return AVERROR(ENOSYS);
                }
                out[(size_t)(*samples + i) * channels + c] = to_s16(sample);
            }
        *samples += n;
        av_frame_unref(f);
    }
    return r == AVERROR(EAGAIN) || r == AVERROR_EOF ? 0 : r;
}
