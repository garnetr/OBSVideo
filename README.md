# YouTube Lower Left

A full-screen capture is too small to read on YouTube. This OBS setup records only a 960×540 point window in the lower left and scales it to 1920×1080, so SF Mono Terminal Regular 12 is about twice as tall in the video. The selfie camera is a circle in the upper right.

The scene collection and profile are already installed on this Mac. Both are named **YouTube Lower Left**.

## Open OBS

Allow Screen Recording and Camera if macOS asks. Quit OBS, then open it again. macOS does not turn those permissions on until the next launch.

The preview should show the lower-left of the screen, filling the frame, with a round camera in the upper right. The old **Untitled** collection is still there if you want it: Scene Collection → Untitled.

## Put a window on the stage

The stage is a 960×540 point window just above the Dock. `place-stage.sh` reads the rectangle the installer saved for this screen. On a Mac introduced in 2024 or later, running macOS 26.2 or later, Edge Light can turn on by itself in a dark room, so the installer sets the stage 94 points in from the left. An older Mac keeps the stage on the left edge. On this M5 Pro that is position 94, 707.

The top of the screen and the entire right side stay off camera. Leave OBS, notes, and chat up there.

From this folder:

```bash
./place-stage.sh terminal
./place-stage.sh chrome
./place-stage.sh safari
./place-stage.sh front
```

`front` moves whichever app is in front. At SF Mono Terminal Regular 12, a Terminal window filled to the stage is **131 columns by 32 rows**. The Clear Dark profile (120×30) fits inside that. A 49-line window is taller than the stage, so those extra lines are not in the video. Thirty-two lines at this size is what stays readable after YouTube compresses the picture.

The circle covers the upper right of the stage: about the last 20 characters of the top 9 lines. Keep the cursor, and the line you are talking about, out of that corner.

For a browser, leave the page zoom at 100%. The 2× scale is what makes the page legible. Command-Plus makes it larger still, for you and for the viewer.

## Circle opacity

The face in the ring is the **Circle** filter on **Selfie Cam**. Right-click Selfie Cam in the Sources list and choose Filters. Click **Circle**. The Opacity slider runs from 0 to 100.

100 fills the ring with you. A lower number lets the stage show through the circle, so the terminal or page stays readable in that corner while you are still visible. At 0 the circle is clear. The ring stays, the black terminal shows through it, and the camera light can still be on.

A new install starts at 100. Leave the slider where you want it for the recording. The change applies immediately in the preview.

## Record

The video is 1920×1080 at 60 fps. Start Recording writes a high-quality MP4 to `~/Movies`, using the Apple hardware encoder. Upload that file to YouTube.

The Mic/Aux track is the laptop microphone, with noise suppression and a light compressor. Sound playing on the Mac, such as a YouTube video you are showing, comes from the Stage source. Use headphones while that sound is playing so the microphone does not record the speakers. Mute Stage in the audio mixer when you want voice only.

## The other Mac

Quit OBS on the M5 Pro, copy this folder over, and run:

```bash
python3 install-obs-setup.py
```

The installer reads that machine's model, display, Dock, and built-in camera, then writes the scene again. Use `place-stage.sh` the same way. It uses the current screen mode, including a Retina framebuffer that is larger than the point size shown in System Settings. An M5 Air gets the same Edge Light inset as this M5 Pro. A Mac from before 2024 does not. Pass `--edge-inset` to force the 94-point inset, `--edge-inset 0` to leave the stage on the left edge, or `--edge-inset 120` to set another width. If the Dock height is different, the installer places the stage above it.

Run the installer again on either Mac any time the Dock size or the screen mode changes. Quit OBS first. OBS overwrites the scene file on the way out.

## OBS 26

OBS 26.1.2, from January 2021, does not show this stage on macOS 13. On the 2018 MacBook Pro (MacBookPro15,1, macOS 13.1), Display Capture never created the Stage source. The preview stayed blank, Properties for Stage had nothing in it, and the camera circle could still appear. That build has no Screen Capture source, which is what the installer writes.

Install OBS 33.0.0 first. It needs macOS 13 or newer. On an Intel Mac, use the Intel build. Check for Updates in 26.1.2 offers 33.0.0. Quit OBS, run the installer, and open OBS 33. The YouTube Lower Left scene loads there, stage included.

## If the picture is wrong

A black preview means Screen Recording is off. Turn it on in System Settings → Privacy & Security → Screen Recording, then relaunch OBS.

An empty circle, with the ring still visible and the camera light on, means Circle opacity is at the bottom of the slider. Open it as described above and raise it.

If the circle is an oval, or the face is sliced off, select Selfie Cam, open Properties, and set the preset to 1920×1080. The Crop to square filter should remove 420 pixels from the left and 420 from the right. Turn off Center Stage if the face zooms or drifts.
