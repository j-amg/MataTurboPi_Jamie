# Lesson 10 - Workspace

## Goal
This lesson is a working notebook for teachers and students who want one place to try the V2 robot library.

It uses `student_robot_v2` and gives examples for the explicit V2 API surface. The notebook is for experimenting. This README is the reference sheet.

## Start here

```python
from lesson_header import *

show_v2_status()
myRobot = bot(base_speed=300)
```

Main stop command:

```python
myRobot.stop()
```

## Top-level V2 robot calls

### Create or reuse the robot

```python
myRobot = bot(base_speed=300, rate_hz=20, prefer_student_moves=False, verbose=True)
```

### Stop the robot

```python
myRobot.stop()
myRobot.move.stop()
```

### Horn

```python
myRobot.horn()
myRobot.buzzer.horn()
```

### Status and versions

```python
myRobot.status()
myRobot.versions()
myRobot.show_versions()
show_v2_status()
show_v2_versions()
```

### Animation object

`myRobot.anim` gives the animation helper object. It is useful for classroom demos and personality work.

```python
myRobot.anim.stop()
myRobot.anim.start_fidget()
myRobot.anim.stop_fidget()
```

## `myRobot.move`

### Basic movement

```python
myRobot.move.forward(seconds=0.5, speed=100)
myRobot.move.backward(seconds=0.5, speed=100)
myRobot.move.left(seconds=0.5, speed=100)
myRobot.move.right(seconds=0.5, speed=100)
myRobot.move.turn_left(seconds=0.5, speed=100)
myRobot.move.turn_right(seconds=0.5, speed=100)
```

### Diagonal and drift movement

```python
myRobot.move.diagonal_left(seconds=0.8, speed=100)
myRobot.move.diagonal_right(seconds=0.8, speed=100)
myRobot.move.drift_left(seconds=1.0, speed=100, turn_blend=0.55)
myRobot.move.drift_right(seconds=1.0, speed=100, turn_blend=0.55)
```

## `myRobot.eyes`

### Set both eyes

```python
myRobot.eyes.color(0, 255, 0)
myRobot.eyes.set_color(0, 255, 0)
myRobot.eyes.set_both(0, 0, 255)
myRobot.eyes.on()
myRobot.eyes.on(255, 100, 0)
```

### Set left or right eye

```python
myRobot.eyes.left(255, 0, 0)
myRobot.eyes.right(0, 0, 255)
```

### Turn eyes off

```python
myRobot.eyes.off()
```

### Blink and wink

```python
myRobot.eyes.blink(every_s=3.0, blank_s=0.5)
myRobot.eyes.start_blink(every_s=2.0, blank_s=0.3)
myRobot.eyes.blink_once(blank_s=0.2)
myRobot.eyes.stop_blink()
myRobot.eyes.wink(side="left", blank_s=0.4)
```

## `myRobot.camera`

### Centre the camera

```python
myRobot.camera.center()
myRobot.camera.center_all()
```

### Move or look in one direction

```python
myRobot.camera.left(amplitude=250, hold_s=0.15)
myRobot.camera.right(amplitude=250, hold_s=0.15)
myRobot.camera.up(amplitude=250, hold_s=0.15)
myRobot.camera.down(amplitude=250, hold_s=0.15)
```

### Glance and look helpers

```python
myRobot.camera.glance_left(amplitude=250, hold_s=0.15)
myRobot.camera.glance_right(amplitude=250, hold_s=0.15)
myRobot.camera.look_left(amplitude=250, hold_s=0.15)
myRobot.camera.look_right(amplitude=250, hold_s=0.15)
myRobot.camera.look_up(amplitude=250, hold_s=0.15)
myRobot.camera.look_down(amplitude=250, hold_s=0.15)
```

### Camera gestures

```python
myRobot.camera.nod(depth=250, speed_s=0.15)
myRobot.camera.shake(width=250, speed_s=0.15)
myRobot.camera.wiggle(cycles=2, amplitude=200, speed_s=0.12)
myRobot.camera.tiny_wiggle(seconds=2.0, amplitude=90, speed_s=0.12)
```

## `myRobot.vision`

### Capture a camera image

```python
picture = myRobot.vision.capture()
picture = myRobot.vision.capture(show=False, save_path="capture.png")
```

### Calibrate and set colour profiles

```python
myRobot.vision.calibrate_color("green")

myRobot.vision.set_color_profile(
    "green",
    lower_hsv=(47, 98, 98),
    upper_hsv=(71, 238, 238),
)

myRobot.vision.get_color_profile("green")
myRobot.vision.show_profiles()
```

### Show and find colour objects

```python
myRobot.vision.show_color("green")
result = myRobot.vision.find_color("green", show=True)
result = myRobot.vision.which_object("green", show=True)
```

### Decide where the target is

```python
decision = myRobot.vision.target_position("green", deadzone=50, show=True)
print(decision["direction"])
print(decision["error"])
```

Possible directions:

```python
"left"
"right"
"center"
"lost"
```

### Move towards a colour automatically

```python
myRobot.vision.move_towards_color(
    "green",
    sideways_seconds=0.15,
    speed=80,
    deadzone=50,
)

myRobot.vision.move_towards_color(
    "green",
    sideways_seconds=0.15,
    speed=80,
    deadzone=50,
    push_seconds=0.6,
    push_speed=100,
)
```

### Face detection

```python
myRobot.vision.detect_faces()
myRobot.vision.show_faces()
myRobot.vision.recognize_faces()
```

### Hand detection

```python
myRobot.vision.recognize_hands()
myRobot.vision.show_hands()
```

### Pose detection

```python
myRobot.vision.detect_pose()
myRobot.vision.show_pose()
myRobot.vision.recognize_pose()
```

## `myRobot.voice`

### Speak text

```python
myRobot.voice.say("Hello")
myRobot.voice.speak("Hello")
```

### List or choose voices

```python
myRobot.voice.voices()
myRobot.voice.show_voices()
myRobot.voice.select("p225")
myRobot.voice.select_voice(number=1)
myRobot.voice.select_voice_number(1)
```

### Volume

```python
myRobot.voice.set_volume(60)
myRobot.voice.get_volume()
```

### Generate and play saved phrases

```python
myRobot.voice.generate("hello_key", "Hello class")
myRobot.voice.generate_phrase("ready_key", "Ready to start")
myRobot.voice.play("hello_key")
myRobot.voice.play_phrase("ready_key")
```

## `myRobot.buzzer`

### Horn and beep

```python
myRobot.buzzer.horn()
myRobot.buzzer.beep()
```

### Notes and melodies

```python
myRobot.buzzer.play_notes("C4:1 D4:1 E4:2", bpm=120)
myRobot.buzzer.play_notes_music_mode("C4 D4 E4 G4", bpm=120)
myRobot.buzzer.play_melody(["C4", "E4", "G4", "C5"], bpm=120)
```

## `myRobot.sonar`

### Wait for a reading

```python
myRobot.sonar.wait()
```

### Read distance

```python
cm = myRobot.sonar.distance_cm()
mm = myRobot.sonar.distance_mm()
```

When the sonar read fails, the V2 wrapper returns `0`.

### Compare distance

```python
if myRobot.sonar.is_closer_than(20):
    myRobot.stop()
```

Aliases:

```python
myRobot.ultrasonic.distance_cm()
myRobot.ultra.distance_cm()
```

## Common classroom patterns

### Move, then stop

```python
myRobot.move.forward(seconds=0.5, speed=100)
myRobot.stop()
```

### React to distance

```python
distance = myRobot.sonar.distance_cm()
if distance < 20:
    myRobot.move.backward(seconds=0.4, speed=90)
```

### React to camera direction

```python
decision = myRobot.vision.target_position("green", deadzone=50)

if decision["direction"] == "left":
    myRobot.move.left(seconds=0.15, speed=80)
elif decision["direction"] == "right":
    myRobot.move.right(seconds=0.15, speed=80)
elif decision["direction"] == "center":
    myRobot.move.forward(seconds=0.6, speed=100)
else:
    myRobot.stop()
```

## Notes

- The V2 wrapper exposes the most important robot actions under one object: `myRobot`.
- Some features need matching ROS services or nodes to be running on the robot image.
