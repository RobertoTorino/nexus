<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Console Link: the stream's threads

How Console Link keeps picture, sound and controller in step during a stream, why Python's global
interpreter lock (the GIL) matters for it, and how to measure it. For the app itself, see its
[manual](../apps/consoles.md).

## The threads

| Thread | Language | What it does |
|---|---|---|
| Receiver | Rust (native core) | Receives the stream's packets, checks and decrypts them, rebuilds frames with FEC, acknowledges, sends the congestion reports. |
| Feedback | Rust (native core) | Sends the controller state at least every 200 ms and the button history. |
| Stream | Python | Takes frames and sound from the receiver (`next_event`), decodes them (native core, FFmpeg), hands the newest picture to the window and the sound to the sound buffer. |
| Window (GUI) | Python + Qt | Draws the picture (texture upload, Y'CbCr to RGB in a shader), and feeds the sound output: Qt's `QAudioSink` pulls from the sound buffer in this thread. |
| Controller | Python | Reads the controllers through SDL3 every 4 ms and hands the state to the feedback thread. |
| Control | Python | Answers the session's heartbeats. |
| Statistics | Python | Writes the statistics file, once a second. |

## The GIL

Only one thread runs Python code at a time: the one holding the GIL. A call into the native core keeps the GIL
unless the core lets go of it (`py.allow_threads` in PyO3), and while it keeps it, every other Python thread waits.

Decoding a 1080p H.264 frame in software takes about 5 ms on the BC-250. At 60 frames per second that is about
300 ms of every second. While the decoder kept the GIL:

- the window could not draw or feed the sound output, whose buffer holds only 30 ms: when it ran empty, the sound
  stuttered;
- pictures were drawn late and unevenly: the picture lagged and stuttered;
- the controller thread's reads waited: the controller felt slow.

The native core now lets go of the GIL in the video decoder, the picture copy (`image()`) and the sound decoder.
They work on their own data and touch no Python object meanwhile. Measured on a BC-250 with a PS4 Pro at 1080p and
60 frames per second (Lumines Remastered, from the Steam shortcut, full screen, network cable): the stutter in
sound and picture was gone and the controller felt more responsive.

The rule for the native core: every call that can take more than a fraction of a millisecond (decoding, copying a
picture, waiting for a packet, a network handshake) lets go of the GIL. `next_event` and `connect` already did.

## Lost packets

The receiver (Rust, `video.rs`) rebuilds a frame from the console's spare FEC packets when a few of its packets are
lost. When too many are, or a frame never arrives, two things keep the decoder from drawing garbage, both the
reference's: `bitstream.rs` reads each frame's first slice header (key frame or not, and which earlier frame it
refers to), and the receiver keeps the last 16 frames it handed out. A frame whose reference is not among them is
not handed out (for HEVC it may be pointed at an older one instead). After a frame FEC could not rebuild, the console
is asked for a key frame (IDRREQUEST) and the frames until it comes are skipped; when none has come after 60 frames,
it is asked for again. The console is also told about every missing frame (CORRUPTFRAME) and may answer by referring
to an older frame.

To try it on a network that loses nothing, the direct start takes a hidden option that drops a share of the video
packets on arrival: `bc250-console-link --stream "<console>" --simulate-loss 5` (percent). The terminal shows the
log as it happens and the statistics file has the recovery per second.

## Measuring it

Each stream writes a statistics file, one line per second, in `~/.local/state/bc250-console-link/streams/`
(`stream_stats.py`; the [manual](../apps/consoles.md#when-it-does-not-work) explains it for users). What to look
for:

| Field | Healthy | What a bad value points to |
|---|---|---|
| `in … longest gap` | about 17 ms at 60 fps | The network or the console: frames arrive in bursts. |
| `recovery` | all 0 | Frames FEC could not rebuild, key frames asked for, frames skipped until one came, frames without their reference: the network loses packets (Wi-Fi, a busy link). A few now and then are handled; many point to the network. |
| `decode avg / max` | well under the frame time (16.7 ms at 60 fps) | The decoder is too slow for the resolution: a lower resolution, a hardware decoder (VA-API), or decoder threads. |
| `shown / skipped` | shown close to the frames in, few skipped | The window draws slower than the frames come. |
| `age avg / max` | a few ms | Time from decoder to drawing: the window is busy. |
| `window late max` | a few ms | The GUI thread is blocked (a native call keeping the GIL, a slow paint). |
| `sound buffer / gaps` | buffer 10 to 40 ms, gaps 0 | Gaps: the sound output was not fed in time (see the window). |
| `controller … longest gap` | about 4 to 6 ms | The controller thread is blocked. |
| `cpu … busiest core / threads` | the busiest core well below 100% | One thread at its limit; more cores do not help a single thread. |
| `disk wait / swapped` | 0 | The board is short of memory and swaps: a slow drive makes it worse. |

On other hardware the same holds. A device with a hardware video decoder (VA-API) decodes cheaply, but copying the
picture out remains. A larger picture costs more everywhere. Compare a file from each device: the fields above show
which part falls behind.
