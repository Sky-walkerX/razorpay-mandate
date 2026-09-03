/**
 * Park the real macOS pointer outside the capture region.
 *
 * ffmpeg's `-capture_cursor 0` does not suppress the pointer on macOS 26 --
 * measured, it appears in frame anyway -- and the real pointer never moves
 * during a take, because Playwright drives the page over CDP rather than the
 * OS. So a motionless arrow would sit in the middle of every frame, next to the
 * synthetic one that is actually doing the work.
 *
 * CGWarpMouseCursorPosition moves it without synthesising a click or a drag.
 * Reached through ctypes so this needs no package that is not already here.
 */
import { spawnSync } from 'node:child_process';

export function parkPointer(x, y) {
  const py = `
import ctypes, ctypes.util
cg = ctypes.CDLL(ctypes.util.find_library('CoreGraphics'))
class P(ctypes.Structure):
    _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]
cg.CGWarpMouseCursorPosition.argtypes = [P]
cg.CGWarpMouseCursorPosition(P(${x}.0, ${y}.0))
print('parked')
`;
  const r = spawnSync('python3', ['-c', py], { encoding: 'utf8' });
  return r.status === 0 && r.stdout.includes('parked');
}

/**
 * Keep the browser the frontmost window for the whole take.
 *
 * avfoundation captures the composited screen, so whatever sits on top of the
 * crop region is what lands in the file. A full take is nearly seven minutes,
 * and one editor notification arriving in the middle of it is enough to record
 * an IDE instead of the product -- which is exactly what happened on the first
 * attempt.
 *
 * page.bringToFront() is not enough: it raises the tab inside Chromium, not
 * Chromium above another application. `open -a` on the app bundle does the
 * OS-level activation, needs no Accessibility permission, and is a no-op when
 * the app is already frontmost.
 */
export function raiseApp(appPath) {
  spawnSync('open', ['-a', appPath], { stdio: 'ignore' });
}

/**
 * Hold both invariants for the whole take: the browser stays frontmost, and the
 * real pointer stays outside the crop.
 *
 * Parking once before launch is not enough. On a six-minute take the real
 * pointer was measured back inside the frame by the last shot, sitting
 * motionless beside the synthetic one. Whatever nudged it -- a trackpad brush,
 * the OS repositioning it on an app switch -- re-parking on the same heartbeat
 * defeats all of them, and warping a pointer that is already parked is free.
 *
 * Warping cannot disturb the page: Playwright drives the mouse over CDP, and
 * those events are synthetic and independent of where the OS pointer sits.
 */
export function keepFrontmost(appPath, park, everyMs = 2000) {
  const beat = () => {
    raiseApp(appPath);
    if (park) parkPointer(park.x, park.y);
  };
  beat();
  const t = setInterval(beat, everyMs);
  t.unref?.();
  return () => clearInterval(t);
}
