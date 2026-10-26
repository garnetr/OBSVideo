#!/usr/bin/env python3
"""Install the YouTube Lower Left OBS scene on this Mac.

The stage is a 960x540 point window in the lower left of the visible screen
(above the Dock). OBS scales that region to a 1920x1080 frame. A circular
selfie cam sits in the upper right of the video.

Run it again on the other Mac, or after the resolution or Dock changes.
It rewrites the display, camera, and crop for whatever screen it finds.
Quit OBS first. The crop uses the display mode's pixel size, which is
what OBS captures. On a scaled Retina mode that is larger than the point
size CGDisplayPixelsWide reports.
"""

import json
import math
import struct
import subprocess
import uuid
import zlib
from pathlib import Path

HOME = Path.home()
OBS_ROOT = HOME / "Library/Application Support/obs-studio"
SCENES = OBS_ROOT / "basic/scenes"
PROFILES = OBS_ROOT / "basic/profiles"
SUPPORT = OBS_ROOT / "youtube-lower-left"
USER_INI = OBS_ROOT / "user.ini"

COLLECTION = "YouTube Lower Left"
PROFILE = "YouTube Lower Left"
CANVAS_W = 1920
CANVAS_H = 1080
# 960x540 points. A 1x framebuffer captures 960x540 and scales 2x.
# A 2x Retina framebuffer captures 1920x1080 and scales 1x.
STAGE_W = 960
STAGE_H = 540
CAM_D = 300
CAM_MARGIN = 36
CAM_PRESET_W = 1920
CAM_PRESET_H = 1080
MASK_SIZE = 1080
PREV_VER = 536870916
CANVAS_UUID = "6c69626f-6273-4c00-9d88-c5136d61696e"
# Opaque #1A1A1A, ARGB, the order OBS color sources use.
BACKDROP = 0xFF1A1A1A


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)


def obs_is_running():
    proc = subprocess.run(["pgrep", "-x", "OBS"], capture_output=True)
    return proc.returncode == 0


def display_uuid():
    src = r"""
    #include <dlfcn.h>
    #include <stdio.h>
    #include <CoreFoundation/CoreFoundation.h>
    #include <CoreGraphics/CoreGraphics.h>
    typedef CFUUIDRef (*make_uuid_fn)(uint32_t);
    int main(void) {
        dlopen("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics", RTLD_LAZY);
        make_uuid_fn make_uuid = (make_uuid_fn)dlsym(RTLD_DEFAULT, "CGDisplayCreateUUIDFromDisplayID");
        if (!make_uuid) return 1;
        CGDirectDisplayID id = CGMainDisplayID();
        CFUUIDRef uuid = make_uuid(id);
        if (!uuid) return 2;
        CFStringRef s = CFUUIDCreateString(NULL, uuid);
        char buf[128];
        if (!CFStringGetCString(s, buf, sizeof buf, kCFStringEncodingUTF8)) return 3;
        printf("%s\n", buf);
        return 0;
    }
    """
    c_path = Path("/tmp/obs-display-uuid.c")
    bin_path = Path("/tmp/obs-display-uuid")
    c_path.write_text(src)
    subprocess.run(
        ["clang", "-framework", "CoreFoundation", "-framework", "CoreGraphics", str(c_path), "-o", str(bin_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return run([str(bin_path)]).stdout.strip()


def screen_and_camera():
    swift = r"""
import AppKit
import AVFoundation
let s = NSScreen.main!
let f = s.frame
let v = s.visibleFrame
print(String(format: "points %.3f %.3f", f.size.width, f.size.height))
print(String(format: "visible %.3f %.3f %.3f %.3f", v.origin.x, v.origin.y, v.size.width, v.size.height))
let session = AVCaptureDevice.DiscoverySession(
    deviceTypes: [.builtInWideAngleCamera],
    mediaType: .video,
    position: .unspecified)
for d in session.devices {
    let name = d.localizedName.replacingOccurrences(of: "\n", with: " ")
    print("camera \(d.uniqueID) \(name)")
}
"""
    out = run(["swift", "-e", swift]).stdout.splitlines()
    points = None
    visible = None
    camera = None
    for line in out:
        parts = line.split()
        if line.startswith("points "):
            points = (float(parts[1]), float(parts[2]))
        elif line.startswith("visible "):
            visible = tuple(float(p) for p in parts[1:5])
        elif line.startswith("camera ") and camera is None:
            camera = (parts[1], " ".join(parts[2:]))
    if points is None or visible is None:
        raise SystemExit(f"Could not read the screen.\n{out}")
    return points, visible, camera


def pixel_size():
    # OBS sizes the display capture with CGDisplayModeGetPixelWidth/Height.
    # CGDisplayPixelsWide returns points on a scaled Retina mode, so a crop
    # built from it lands in the middle of the framebuffer.
    swift = r"""
import CoreGraphics
let id = CGMainDisplayID()
guard let mode = CGDisplayCopyDisplayMode(id) else {
    fputs("no display mode\n", stderr)
    exit(1)
}
print("\(mode.pixelWidth) \(mode.pixelHeight)")
"""
    parts = run(["swift", "-e", swift]).stdout.split()
    return int(parts[0]), int(parts[1])


def stage_geometry(points, visible, pixels):
    point_w, point_h = points
    vis_x, vis_y, vis_w, vis_h = visible
    pixel_w, pixel_h = pixels
    # NSScreen origin is the bottom left. Convert the visible frame
    # (everything not under the menu bar or Dock) to top-left coordinates.
    vis_top = point_h - (vis_y + vis_h)
    stage_w = float(STAGE_W)
    stage_h = float(STAGE_H)
    if stage_w > vis_w or stage_h > vis_h:
        if vis_w / vis_h > 16 / 9:
            stage_h = vis_h
            stage_w = vis_h * 16 / 9
        else:
            stage_w = vis_w
            stage_h = vis_w * 9 / 16
    left = vis_x
    top = vis_top + vis_h - stage_h
    right = left + stage_w
    bottom = top + stage_h

    sx = pixel_w / point_w
    sy = pixel_h / point_h
    crop_left = int(round(left * sx))
    crop_top = int(round(top * sy))
    crop_right = int(pixel_w - round(right * sx))
    crop_bottom = int(pixel_h - round(bottom * sy))
    cap_w = pixel_w - crop_left - crop_right
    cap_h = pixel_h - crop_top - crop_bottom
    if cap_w < 2 or cap_h < 2:
        raise SystemExit(f"Capture region is empty ({cap_w}x{cap_h}).")
    scale_x = CANVAS_W / cap_w
    scale_y = CANVAS_H / cap_h
    return {
        "points": [point_w, point_h],
        "pixels": [pixel_w, pixel_h],
        "visible_cocoa": [vis_x, vis_y, vis_w, vis_h],
        "bounds": [int(round(left)), int(round(top)), int(round(right)), int(round(bottom))],
        "stage_points": [stage_w, stage_h],
        "crop": [crop_left, crop_top, crop_right, crop_bottom],
        "capture_pixels": [cap_w, cap_h],
        "scale": [scale_x, scale_y],
    }


def write_png(path, width, height, pixel):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel(x, y))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def coverage(distance, radius):
    # One-pixel analytic coverage so the edge is not jagged.
    return max(0.0, min(1.0, radius - distance + 0.5))


def make_masks(directory):
    directory.mkdir(parents=True, exist_ok=True)
    mask_path = directory / "circle-mask.png"
    ring_path = directory / "circle-ring.png"
    size = MASK_SIZE
    center = (size - 1) / 2
    radius = size / 2 - 1.5
    # About 5 video pixels once the 1080 square is fit into the 300px circle.
    ring_thickness = 18.0
    ring_outer = radius - 1.0
    ring_inner = ring_outer - ring_thickness

    def mask_px(x, y):
        d = math.hypot(x - center, y - center)
        v = int(round(coverage(d, radius) * 255))
        return bytes((v, v, v, 255))

    def ring_px(x, y):
        d = math.hypot(x - center, y - center)
        outer = coverage(d, ring_outer)
        inner = coverage(d, ring_inner)
        a = max(0.0, min(1.0, outer - inner))
        return bytes((255, 255, 255, int(round(a * 255))))

    write_png(mask_path, size, size, mask_px)
    write_png(ring_path, size, size, ring_px)
    return mask_path, ring_path


def uid():
    return str(uuid.uuid4())


def pos_rel(x, y):
    half_h = CANVAS_H / 2
    return {"x": (x - CANVAS_W / 2) / half_h, "y": (y - CANVAS_H / 2) / half_h}


def source(name, source_id, settings, filters=None, mixers=255, muted=False, volume=1.0, version=None, hotkeys=None):
    obj = {
        "prev_ver": PREV_VER,
        "name": name,
        "uuid": uid(),
        "id": source_id,
        "versioned_id": source_id,
        "settings": settings,
        "mixers": mixers,
        "sync": 0,
        "flags": 0,
        "volume": volume,
        "balance": 0.5,
        "enabled": True,
        "muted": muted,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": hotkeys
        or {
            "libobs.mute": [],
            "libobs.unmute": [],
            "libobs.push-to-mute": [],
            "libobs.push-to-talk": [],
        },
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
    }
    if version is not None:
        obj["version"] = version
    if filters:
        obj["filters"] = filters
    return obj


def scene_item(name, source_uuid, item_id, pos, scale, crop, scale_filter):
    x, y = pos
    sx, sy = scale
    return {
        "name": name,
        "source_uuid": source_uuid,
        "visible": True,
        "locked": True,
        "rot": 0.0,
        "scale_ref": {"x": float(CANVAS_W), "y": float(CANVAS_H)},
        "align": 5,
        "bounds_type": 0,
        "bounds_align": 0,
        "bounds_crop": False,
        "crop_left": int(crop[0]),
        "crop_top": int(crop[1]),
        "crop_right": int(crop[2]),
        "crop_bottom": int(crop[3]),
        "id": item_id,
        "group_item_backup": False,
        "pos": {"x": float(x), "y": float(y)},
        "pos_rel": pos_rel(x, y),
        "scale": {"x": float(sx), "y": float(sy)},
        "scale_rel": {"x": float(sx), "y": float(sy)},
        "bounds": {"x": 0.0, "y": 0.0},
        "bounds_rel": {"x": 0.0, "y": 0.0},
        "scale_filter": scale_filter,
        "blend_method": "default",
        "blend_type": "normal",
        "show_transition": {"duration": 0},
        "hide_transition": {"duration": 0},
        "private_settings": {},
    }


def build_collection(geom, display, camera, mask_path, ring_path):
    side = (CAM_PRESET_W - CAM_PRESET_H) // 2
    cam_scale = CAM_D / float(MASK_SIZE)
    cam_x = CANVAS_W - CAM_MARGIN - CAM_D
    cam_y = CAM_MARGIN

    crop_filter = source(
        "Crop to square",
        "crop_filter",
        {"relative": True, "left": side, "top": 0, "right": side, "bottom": 0},
        mixers=0,
    )
    mask_filter = source(
        "Circle",
        "mask_filter",
        {
            "type": "mask_color_filter.effect",
            "image_path": str(mask_path),
            "color": 16777215,
            # mask_filter v1. The slider is an integer 0–100. A float such
            # as 1.0 is read as 1, which leaves the face almost invisible.
            "opacity": 100,
            "stretch": True,
        },
        mixers=0,
    )
    backdrop = source(
        "Backdrop",
        "color_source",
        {"color": BACKDROP, "width": CANVAS_W, "height": CANVAS_H},
        mixers=0,
    )
    stage = source(
        "Stage",
        "screen_capture",
        {
            "type": 0,
            "display_uuid": display,
            "show_cursor": True,
            "hide_obs": True,
            "show_empty_names": False,
            "show_hidden_windows": False,
            "application": "",
            "window": 0,
        },
        volume=1.0,
    )
    cam_settings = {
        "use_preset": True,
        "preset": "AVCaptureSessionPreset1920x1080",
        "buffering": True,
        "enable_audio": False,
    }
    if camera:
        cam_settings["device"] = camera[0]
        cam_settings["device_name"] = camera[1]
    selfie = source(
        "Selfie Cam",
        "macos-avcapture",
        cam_settings,
        filters=[crop_filter, mask_filter],
        muted=True,
        volume=0.0,
    )
    ring = source("Cam Ring", "image_source", {"file": str(ring_path), "unload": False}, mixers=0)

    items = [
        scene_item("Backdrop", backdrop["uuid"], 1, (0, 0), (1, 1), (0, 0, 0, 0), "disable"),
        scene_item(
            "Stage",
            stage["uuid"],
            2,
            (0, 0),
            geom["scale"],
            geom["crop"],
            "lanczos",
        ),
        scene_item("Selfie Cam", selfie["uuid"], 3, (cam_x, cam_y), (cam_scale, cam_scale), (0, 0, 0, 0), "area"),
        scene_item("Cam Ring", ring["uuid"], 4, (cam_x, cam_y), (cam_scale, cam_scale), (0, 0, 0, 0), "disable"),
    ]
    hotkeys = {"OBSBasic.SelectScene": []}
    for item_id in range(1, 5):
        hotkeys[f"libobs.show_scene_item.{item_id}"] = []
        hotkeys[f"libobs.hide_scene_item.{item_id}"] = []
    scene = source(
        "Lower Left",
        "scene",
        {"id_counter": 5, "custom_size": False, "items": items},
        mixers=0,
        hotkeys=hotkeys,
    )
    scene["canvas_uuid"] = CANVAS_UUID

    mic_filters = [
        source(
            "Noise Suppression",
            "noise_suppress_filter",
            {"method": "rnnoise", "suppress_level": -30},
            mixers=0,
        ),
        source(
            "Compressor",
            "compressor_filter",
            {
                "ratio": 3.0,
                "threshold": -18.0,
                "attack_time": 10,
                "release_time": 100,
                "output_gain": 2.0,
                "sidechain_source": "",
            },
            mixers=0,
        ),
    ]
    mic = source("Mic/Aux", "coreaudio_input_capture", {"device_id": "default"}, filters=mic_filters)

    return {
        "AuxAudioDevice1": mic,
        "current_scene": "Lower Left",
        "current_program_scene": "Lower Left",
        "scene_order": [{"name": "Lower Left"}],
        "name": COLLECTION,
        "sources": [scene, backdrop, stage, selfie, ring],
        "groups": [],
        "quick_transitions": [
            {"name": "Cut", "duration": 300, "hotkeys": [], "id": 1, "fade_to_black": False},
            {"name": "Fade", "duration": 300, "hotkeys": [], "id": 2, "fade_to_black": False},
            {"name": "Fade", "duration": 300, "hotkeys": [], "id": 3, "fade_to_black": True},
        ],
        "transitions": [],
        "saved_projectors": [],
        "canvases": [],
        "current_transition": "Fade",
        "transition_duration": 300,
        "preview_locked": False,
        "scaling_enabled": False,
        "scaling_level": 0,
        "scaling_off_x": 0.0,
        "scaling_off_y": 0.0,
        "virtual-camera": {"type2": 3},
        "modules": {
            "scripts-tool": [],
            "output-timer": {
                "streamTimerHours": 0,
                "streamTimerMinutes": 0,
                "streamTimerSeconds": 30,
                "recordTimerHours": 0,
                "recordTimerMinutes": 0,
                "recordTimerSeconds": 30,
                "autoStartStreamTimer": False,
                "autoStartRecordTimer": False,
                "pauseRecordTimer": True,
            },
            "auto-scene-switcher": {
                "interval": 300,
                "non_matching_scene": "",
                "switch_if_not_matching": False,
                "active": False,
                "switches": [],
            },
        },
        "version": 2,
    }


def write_profile():
    profile_dir = PROFILES / PROFILE
    profile_dir.mkdir(parents=True, exist_ok=True)
    movies = HOME / "Movies"
    ini = f"""[General]
Name={PROFILE}

[Output]
Mode=Simple
FilenameFormatting=%CCYY-%MM-%DD %hh-%mm-%ss
DelayEnable=false
DelaySec=20
DelayPreserve=true
Reconnect=true
RetryDelay=2
MaxRetries=25
BindIP=default
IPFamily=IPv4+IPv6
NewSocketLoopEnable=false
LowLatencyEnable=false

[Stream1]
IgnoreRecommended=false
EnableMultitrackVideo=false
MultitrackVideoMaximumAggregateBitrateAuto=true
MultitrackVideoMaximumVideoTracksAuto=true

[SimpleOutput]
FilePath={movies}
RecFormat2=hybrid_mp4
VBitrate=9000
ABitrate=192
UseAdvanced=false
Preset=veryfast
NVENCPreset2=p5
RecQuality=HQ
RecRB=false
RecRBTime=20
RecRBSize=512
RecRBPrefix=Replay
StreamAudioEncoder=aac
RecAudioEncoder=aac
RecTracks=1
StreamEncoder=apple_h264
RecEncoder=apple_h264

[AdvOut]
ApplyServiceSettings=true
UseRescale=false
TrackIndex=1
VodTrackIndex=2
Encoder=obs_x264
RecType=Standard
RecFilePath={movies}
RecFormat2=hybrid_mp4
RecUseRescale=false
RecTracks=1
RecEncoder=none
FLVTrack=1
StreamMultiTrackAudioMixes=1
FFOutputToFile=true
FFFilePath={movies}
FFExtension=mp4
FFVBitrate=12000
FFVGOPSize=120
FFUseRescale=false
FFIgnoreCompat=false
FFABitrate=192
FFAudioMixes=1
Track1Bitrate=192
Track2Bitrate=192
Track3Bitrate=192
Track4Bitrate=192
Track5Bitrate=192
Track6Bitrate=192
RecSplitFileTime=15
RecSplitFileSize=2048
RecRB=false
RecRBTime=20
RecRBSize=512
AudioEncoder=CoreAudio_AAC
RecAudioEncoder=CoreAudio_AAC

[Video]
BaseCX={CANVAS_W}
BaseCY={CANVAS_H}
OutputCX={CANVAS_W}
OutputCY={CANVAS_H}
FPSType=0
FPSCommon=60
FPSInt=60
FPSNum=60
FPSDen=1
ScaleType=lanczos
ColorFormat=NV12
ColorSpace=709
ColorRange=Partial
SdrWhiteLevel=300
HdrNominalPeakLevel=1000

[Audio]
MonitoringDeviceId=default
MonitoringDeviceName=Default
SampleRate=48000
ChannelSetup=Stereo
MeterDecayRate=23.53
PeakMeterType=0
"""
    (profile_dir / "basic.ini").write_text(ini)


def update_user_ini():
    text = USER_INI.read_text() if USER_INI.exists() else "[Basic]\n"
    lines = text.splitlines()
    keys = {
        "Profile": PROFILE,
        "ProfileDir": PROFILE,
        "SceneCollection": COLLECTION,
        "SceneCollectionFile": f"{COLLECTION}.json",
    }
    in_basic = False
    seen = set()
    out = []
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            if in_basic:
                for key, value in keys.items():
                    if key not in seen:
                        out.append(f"{key}={value}")
                        seen.add(key)
            in_basic = line == "[Basic]"
        if in_basic and "=" in line:
            key = line.split("=", 1)[0]
            if key in keys:
                line = f"{key}={keys[key]}"
                seen.add(key)
        out.append(line)
    if not any(line == "[Basic]" for line in out):
        out.extend(["[Basic]"] + [f"{k}={v}" for k, v in keys.items()])
    elif "[Basic]" in out and not seen:
        # [Basic] was the last section and the loop already flushed... handled above
        pass
    # If [Basic] is the last section, the flush above ran when we never saw a new header.
    # The loop only flushes when a new section starts. Flush now if still missing.
    if "Profile" not in seen:
        if out and out[-1] != "[Basic]" and "[Basic]" in out:
            out.extend([f"{k}={v}" for k, v in keys.items() if k not in seen])
        elif "[Basic]" not in out:
            out.extend(["[Basic]"] + [f"{k}={v}" for k, v in keys.items()])
    USER_INI.write_text("\n".join(out) + "\n")


def main():
    if obs_is_running():
        raise SystemExit("Quit OBS first. It overwrites the scene file when it exits.")
    print("Reading this Mac's display and camera...")
    points, visible, camera = screen_and_camera()
    pixels = pixel_size()
    display = display_uuid()
    geom = stage_geometry(points, visible, pixels)
    SUPPORT.mkdir(parents=True, exist_ok=True)
    mask_path, ring_path = make_masks(SUPPORT)
    project_assets = Path(__file__).resolve().parent / "assets"
    make_masks(project_assets)

    collection = build_collection(geom, display, camera, mask_path, ring_path)
    SCENES.mkdir(parents=True, exist_ok=True)
    scene_path = SCENES / f"{COLLECTION}.json"
    scene_path.write_text(json.dumps(collection, indent=4) + "\n")
    stage_path = SUPPORT / "stage.json"
    stage_doc = {
        "bounds": geom["bounds"],
        "stage_points": geom["stage_points"],
        "capture_pixels": geom["capture_pixels"],
        "scale": geom["scale"],
        "crop": geom["crop"],
        "screen_points": geom["points"],
        "screen_pixels": geom["pixels"],
        "display_uuid": display,
        "camera": {"id": camera[0], "name": camera[1]} if camera else None,
        "canvas": [CANVAS_W, CANVAS_H],
        "circle": {"diameter": CAM_D, "margin": CAM_MARGIN},
    }
    stage_path.write_text(json.dumps(stage_doc, indent=2) + "\n")
    write_profile()
    update_user_ini()

    left, top, right, bottom = geom["bounds"]
    cap_w, cap_h = geom["capture_pixels"]
    sx, sy = geom["scale"]
    print()
    print(f"Scene collection: {scene_path}")
    print(f"Profile:          {PROFILES / PROFILE}")
    print(f"Screen:           {geom['points'][0]:.0f}x{geom['points'][1]:.0f} points, {pixels[0]}x{pixels[1]} pixels")
    print(f"Stage window:     left {left}, top {top}, {right - left:.0f}x{bottom - top:.0f}")
    print(f"Capture:          {cap_w}x{cap_h} pixels, scaled {sx:.3f}x{sy:.3f} to {CANVAS_W}x{CANVAS_H}")
    if camera:
        print(f"Camera:           {camera[1]}")
    else:
        print("Camera:           none found — pick the built-in camera on Selfie Cam")
    print()
    print("Open OBS. Allow Screen Recording and Camera if macOS asks, then quit OBS and open it once more.")
    print("Before you record, put the window on the stage:")
    print("  ./place-stage.sh terminal")
    print("  ./place-stage.sh chrome")


if __name__ == "__main__":
    main()
