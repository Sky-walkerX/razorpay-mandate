/**
 * Screen capture, started and stopped by the driver itself.
 *
 * Owning the capture rather than asking a human to hit record means t=0 in the
 * timing manifest is exactly t=0 in the file, so every cut point in post is
 * computed from a mark the driver wrote rather than eyeballed on a timeline.
 *
 * Why ffmpeg + avfoundation and not `screencapture -v`: on macOS 26 the
 * ScreenCaptureKit video path is gated separately from stills. Measured on this
 * machine, `screencapture -x file.png` succeeds while `screencapture -v` exits 1
 * with no file and no message, whereas avfoundation records fine. Rather than
 * send someone into System Settings to chase a silent denial, use the path that
 * already works.
 *
 * Capture encodes with h264_videotoolbox -- Apple Silicon's hardware encoder --
 * because the CPU is busy driving a browser full of 60fps animation at the same
 * time, and a dropped frame during the take is unrecoverable. Quality is
 * restored by the libx264 pass in post.
 */
import { spawn } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';

/** Index of "Capture screen 0" in avfoundation's device list. */
export async function screenDeviceIndex() {
  return new Promise((resolve) => {
    const p = spawn('ffmpeg', ['-f', 'avfoundation', '-list_devices', 'true', '-i', '']);
    let buf = '';
    p.stderr.on('data', (d) => (buf += d));
    p.on('close', () => {
      const m = buf.match(/\[(\d+)\]\s+Capture screen 0/);
      resolve(m ? Number(m[1]) : 2);
    });
  });
}

export class Recorder {
  /**
   * @param rect  browser window in points {x,y,w,h}
   * @param scale display backing scale (2 on Retina)
   */
  constructor(outPath, rect, { fps = 60, scale = 2, device = 2 } = {}) {
    this.outPath = outPath;
    this.rect = rect;
    this.fps = fps;
    this.scale = scale;
    this.device = device;
    this.proc = null;
    this.t0 = null;
  }

  async start() {
    const { x, y, w, h } = this.rect;
    const s = this.scale;
    // Crop to the browser window in the same pass, so nothing else on the
    // desktop is ever written to disk.
    const crop = `crop=${w * s}:${h * s}:${x * s}:${y * s}`;

    const args = [
      '-y',
      '-f', 'avfoundation',
      '-capture_cursor', '0',        // the real pointer never moves; ours is in the page
      '-framerate', String(this.fps),
      '-i', `${this.device}:none`,
      '-vf', crop,
      '-c:v', 'h264_videotoolbox',
      '-b:v', '40M',
      '-pix_fmt', 'yuv420p',
      this.outPath,
    ];

    this.proc = spawn('ffmpeg', args, { stdio: ['pipe', 'ignore', 'pipe'] });
    this.stderr = '';
    this.proc.stderr.on('data', (d) => { this.stderr += d; });
    this.proc.on('close', (code) => { this.exitCode = code; });

    // avfoundation takes a moment to open the display stream. Starting the
    // clock before it is actually writing frames would skew every mark.
    await new Promise((r) => setTimeout(r, 2500));
    if (this.exitCode != null) {
      throw new Error(
        'capture died on startup:\n' + this.stderr.split('\n').slice(-12).join('\n'),
      );
    }
    this.t0 = Date.now();
    console.log(`  recording ${w * s}x${h * s} @${this.fps}fps -> ${this.outPath}`);
    return this.t0;
  }

  /** Milliseconds since the first recorded frame. */
  now() {
    return this.t0 === null ? 0 : Date.now() - this.t0;
  }

  async stop() {
    if (!this.proc || this.exitCode != null) return;
    // 'q' lets ffmpeg write its moov atom; SIGKILL would leave an unplayable file.
    this.proc.stdin.write('q');
    this.proc.stdin.end();
    await new Promise((resolve) => {
      this.proc.on('close', resolve);
      setTimeout(resolve, 15000);
    });
    if (existsSync(this.outPath)) {
      const mb = (statSync(this.outPath).size / 1e6).toFixed(1);
      console.log(`  stopped. ${this.outPath} (${mb} MB)`);
    } else {
      console.error('  capture wrote no file:\n' + this.stderr.split('\n').slice(-15).join('\n'));
    }
  }
}

/** A recorder that writes nothing, so choreography can be tuned for free. */
export class NullRecorder {
  constructor() { this.t0 = null; }
  async start() { this.t0 = Date.now(); return this.t0; }
  now() { return this.t0 === null ? 0 : Date.now() - this.t0; }
  async stop() {}
}
