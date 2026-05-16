#!/usr/bin/env python3
"""student_robot_v2.py

V2 aggregate robot API.

Design goals:
- single object entry point for lessons: myRobot = bot(...)
- singleton-safe backends so eyes/camera/sonar/TTS are reused reliably
- standardized namespaces for movement, eyes, camera, voice, buzzer, sonar
- still expose the underlying library methods so nothing is lost
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
from pathlib import Path
import threading
from typing import Any, Optional

from ros_service_client import clear_process_singleton, get_process_singleton, set_process_singleton

__version__ = "2.4.2"

_SINGLETON_KEY = "student_robot_v2:robot"
_LOCK_KEY = "student_robot_v2:lock"


def _get_lock() -> threading.Lock:
    lock = getattr(builtins, _LOCK_KEY, None)
    if lock is None:
        lock = threading.Lock()
        setattr(builtins, _LOCK_KEY, lock)
    return lock


def _call_if_callable(fn: Any, *args, **kwargs):
    if callable(fn):
        return fn(*args, **kwargs)
    return None


class _BackendProxy:
    def __init__(self, owner: "RobotV2"):
        self._owner = owner

    def _get_backend(self):
        return None

    def _ensure(self):
        self._owner._ensure_backends()
        return self._get_backend()

    def __getattr__(self, name: str):
        backend = self._ensure()
        if backend is None:
            raise AttributeError(f"Backend unavailable for {type(self).__name__}.{name}")
        return getattr(backend, name)


class MoveNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._move_backend

    def _resolve(self, move_name: str):
        names = self._owner._move_aliases(move_name)
        for backend in self._owner._move_backends:
            if backend is None:
                continue
            for name in names:
                fn = getattr(backend, name, None)
                if callable(fn):
                    return fn
        return None

    def run(self, move_name: str, seconds: float = 0.5, speed: Optional[float] = None, **kwargs):
        fn = self._resolve(move_name)
        if fn is None:
            raise AttributeError(f"Move '{move_name}' is not available")
        effective_speed = float(self._owner.base_speed) if speed is None else float(speed)
        self._owner._status("move", move_name, f"seconds={seconds}", f"speed={effective_speed}")
        return fn(seconds=seconds, speed=speed, **kwargs)

    def forward(self, seconds: float = 0.5, speed: Optional[float] = None):
        return self.run("forward", seconds=seconds, speed=speed)

    def backward(self, seconds: float = 0.5, speed: Optional[float] = None):
        return self.run("backward", seconds=seconds, speed=speed)

    def left(self, seconds: float = 0.5, speed: Optional[float] = None):
        return self.run("left", seconds=seconds, speed=speed)

    def right(self, seconds: float = 0.5, speed: Optional[float] = None):
        return self.run("right", seconds=seconds, speed=speed)

    def turn_left(self, seconds: float = 0.5, speed: Optional[float] = None):
        return self.run("turn_left", seconds=seconds, speed=speed)

    def turn_right(self, seconds: float = 0.5, speed: Optional[float] = None):
        return self.run("turn_right", seconds=seconds, speed=speed)

    def diagonal_left(self, seconds: float = 0.8, speed: Optional[float] = None):
        return self.run("diagonal_left", seconds=seconds, speed=speed)

    def diagonal_right(self, seconds: float = 0.8, speed: Optional[float] = None):
        return self.run("diagonal_right", seconds=seconds, speed=speed)

    def drift_left(self, seconds: float = 1.0, speed: Optional[float] = None, turn_blend: float = 0.55):
        return self.run("drift_left", seconds=seconds, speed=speed, turn_blend=turn_blend)

    def drift_right(self, seconds: float = 1.0, speed: Optional[float] = None, turn_blend: float = 0.55):
        return self.run("drift_right", seconds=seconds, speed=speed, turn_blend=turn_blend)

    def drive_for(self, vx: float, vy: float, seconds: float, speed: Optional[float] = None):
        backend = self._ensure()
        fn = getattr(backend, "drive_for", None)
        if not callable(fn):
            raise AttributeError("drive_for is not available on movement backend")
        return fn(vx=vx, vy=vy, seconds=seconds, speed=speed)

    def stop(self):
        return self._owner.stop()

    def run_async(self, move_name: str, seconds: float = 0.5, speed: Optional[float] = None, **kwargs):
        return self._owner.anim.run_async(self.run, move_name, seconds, speed, **kwargs)

    def use_base(self):
        return self._owner.use_base_moves()

    def use_robot_moves(self):
        return self._owner.use_base_moves()

    def use_student(self):
        return self._owner.use_student_moves()


class EyesNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._eyes_backend

    @staticmethod
    def _rgb_args(r, g=None, b=None):
        if isinstance(r, (tuple, list)):
            if len(r) != 3:
                raise ValueError("RGB tuple/list must have exactly 3 values")
            return int(r[0]), int(r[1]), int(r[2])
        if g is None or b is None:
            raise TypeError("Expected either (r, g, b) or a single (r, g, b) tuple/list")
        return int(r), int(g), int(b)

    def color(self, r: int, g: int = None, b: int = None):
        r, g, b = self._rgb_args(r, g, b)
        self._owner.anim.set_eye_color((r, g, b))

    def set_color(self, r: int, g: int = None, b: int = None):
        return self.color(r, g, b)

    def set_both(self, r: int, g: int = None, b: int = None):
        r, g, b = self._rgb_args(r, g, b)
        backend = self._ensure()
        self._owner.anim.set_eye_color((r, g, b))
        return backend.set_both(r, g, b)

    def left(self, r: int, g: int = None, b: int = None):
        r, g, b = self._rgb_args(r, g, b)
        backend = self._ensure()
        return backend.set_left(r, g, b)

    def right(self, r: int, g: int = None, b: int = None):
        r, g, b = self._rgb_args(r, g, b)
        backend = self._ensure()
        return backend.set_right(r, g, b)

    def off(self):
        backend = self._ensure()
        return backend.off()

    def on(self, r: int = 0, g: int = 255, b: int = 120):
        return self.set_both(r, g, b)

    def blink(self, every_s: float = 3.0, blank_s: float = 0.5):
        return self._owner.anim.start_blinking(every_s=every_s, blank_s=blank_s)

    def start_blink(self, every_s: float = 3.0, blank_s: float = 0.5):
        return self.blink(every_s=every_s, blank_s=blank_s)

    def blink_once(self, blank_s: float = 0.5):
        return self._owner.anim.blink_once(blank_s=blank_s)

    def stop_blink(self):
        return self._owner.anim.stop_blinking()

    def wink(self, side: str = "left", blank_s: float = 0.5):
        return self._owner.anim.wink(side=side, blank_s=blank_s)


class CameraNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._camera_backend

    @staticmethod
    def _clamp_amplitude(amplitude: int) -> int:
        return max(0, min(500, int(amplitude)))

    def center(self):
        backend = self._ensure()
        return backend.center_all()

    def center_all(self):
        return self.center()

    def left(self, amplitude: int = 250, hold_s: float = 0.15):
        backend = self._ensure()
        return backend.set_yaw(backend.center - self._clamp_amplitude(amplitude))

    def right(self, amplitude: int = 250, hold_s: float = 0.15):
        backend = self._ensure()
        return backend.set_yaw(backend.center + self._clamp_amplitude(amplitude))

    def up(self, amplitude: int = 250, hold_s: float = 0.15):
        backend = self._ensure()
        return backend.set_pitch(backend.center + self._clamp_amplitude(amplitude))

    def down(self, amplitude: int = 250, hold_s: float = 0.15):
        backend = self._ensure()
        return backend.set_pitch(backend.center - self._clamp_amplitude(amplitude))

    def glance_left(self, amplitude: int = 250, hold_s: float = 0.15):
        backend = self._ensure()
        return backend.glance_left(amplitude=self._clamp_amplitude(amplitude), hold_s=hold_s)

    def glance_right(self, amplitude: int = 250, hold_s: float = 0.15):
        backend = self._ensure()
        return backend.glance_right(amplitude=self._clamp_amplitude(amplitude), hold_s=hold_s)

    def look_left(self, amplitude: int = 250, hold_s: float = 0.15):
        return self.left(amplitude=amplitude, hold_s=hold_s)

    def look_right(self, amplitude: int = 250, hold_s: float = 0.15):
        return self.right(amplitude=amplitude, hold_s=hold_s)

    def look_up(self, amplitude: int = 250, hold_s: float = 0.15):
        return self.up(amplitude=amplitude, hold_s=hold_s)

    def look_down(self, amplitude: int = 250, hold_s: float = 0.15):
        return self.down(amplitude=amplitude, hold_s=hold_s)

    def nod(self, depth: int = 250, speed_s: Optional[float] = None):
        return self._owner.anim.nod(depth=depth, speed_s=speed_s)

    def shake(self, width: int = 250, speed_s: Optional[float] = None):
        return self._owner.anim.shake(width=width, speed_s=speed_s)

    def wiggle(self, cycles: int = 2, amplitude: int = 200, speed_s: Optional[float] = None):
        backend = self._ensure()
        return backend.wiggle(cycles=cycles, amplitude=amplitude, speed_s=speed_s)

    def tiny_wiggle(self, seconds: float = 2.0, amplitude: int = 90, speed_s: float = 0.12):
        backend = self._ensure()
        return backend.tiny_wiggle(seconds=seconds, amplitude=amplitude, speed_s=speed_s)


class VisionNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._vision_backend

    def capture(self, show: bool = True, save_path: Optional[str] = None, title: str = "Camera Capture"):
        backend = self._ensure()
        return backend.capture(show=show, save_path=save_path, title=title)

    def show_color(self, color: str, show: bool = True, save_path: Optional[str] = None, min_area: Optional[int] = None):
        backend = self._ensure()
        return backend.show_color(color=color, show=show, save_path=save_path, min_area=min_area)

    def find_color(self, color: str, show: bool = True, save_path: Optional[str] = None, min_area: Optional[int] = None):
        return self.show_color(color=color, show=show, save_path=save_path, min_area=min_area)

    def which_object(self, color: str, show: bool = True, save_path: Optional[str] = None, min_area: Optional[int] = None):
        backend = self._ensure()
        return backend.which_object(color=color, show=show, save_path=save_path, min_area=min_area)

    def target_position(
        self,
        color: str,
        target_x: Optional[int] = None,
        deadzone: int = 50,
        show: bool = True,
        min_area: Optional[int] = None,
    ):
        backend = self._ensure()
        return backend.target_position(
            color=color,
            target_x=target_x,
            deadzone=deadzone,
            show=show,
            min_area=min_area,
        )

    def move_towards_color(
        self,
        color: str,
        sideways_seconds: float = 0.15,
        speed: Optional[float] = 80,
        deadzone: int = 50,
        target_x: Optional[int] = None,
        show: bool = False,
        min_area: Optional[int] = None,
        push_seconds: Optional[float] = None,
        push_speed: Optional[float] = None,
    ):
        decision = self.target_position(
            color=color,
            target_x=target_x,
            deadzone=deadzone,
            show=show,
            min_area=min_area,
        )
        direction = decision["direction"]
        decision["moved"] = None

        if direction == "left":
            self._owner.move.left(seconds=sideways_seconds, speed=speed)
            self._owner.move.stop()
            decision["moved"] = "left"
        elif direction == "right":
            self._owner.move.right(seconds=sideways_seconds, speed=speed)
            self._owner.move.stop()
            decision["moved"] = "right"
        elif direction == "center" and push_seconds is not None:
            self._owner.move.forward(
                seconds=float(push_seconds),
                speed=speed if push_speed is None else push_speed,
            )
            self._owner.move.stop()
            decision["moved"] = "forward"

        return decision

    def calibrate_color(
        self,
        color: str,
        box_size: int = 80,
        hue_pad: int = 12,
        sat_pad: int = 70,
        val_pad: int = 70,
        show: bool = True,
        save_path: Optional[str] = None,
        persist: bool = True,
    ):
        backend = self._ensure()
        return backend.calibrate_color(
            color=color,
            box_size=box_size,
            hue_pad=hue_pad,
            sat_pad=sat_pad,
            val_pad=val_pad,
            show=show,
            save_path=save_path,
            persist=persist,
        )

    def set_color_profile(self, color: str, lower_hsv, upper_hsv=None):
        backend = self._ensure()
        return backend.set_color_profile(color=color, lower_hsv=lower_hsv, upper_hsv=upper_hsv)

    def get_color_profile(self, color: str):
        backend = self._ensure()
        return backend.get_color_profile(color=color)

    def show_profiles(self):
        backend = self._ensure()
        return backend.show_profiles()

    def detect_faces(self, show: bool = True, save_path: Optional[str] = None, min_confidence: float = 0.5):
        backend = self._ensure()
        return backend.detect_faces(show=show, save_path=save_path, min_confidence=min_confidence)

    def show_faces(self, show: bool = True, save_path: Optional[str] = None, min_confidence: float = 0.5):
        backend = self._ensure()
        return backend.show_faces(show=show, save_path=save_path, min_confidence=min_confidence)

    def recognize_faces(self, show: bool = True, save_path: Optional[str] = None, min_confidence: float = 0.5):
        backend = self._ensure()
        return backend.recognize_faces(show=show, save_path=save_path, min_confidence=min_confidence)

    def recognize_hands(
        self,
        show: bool = True,
        save_path: Optional[str] = None,
        max_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        backend = self._ensure()
        return backend.recognize_hands(
            show=show,
            save_path=save_path,
            max_hands=max_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def show_hands(
        self,
        show: bool = True,
        save_path: Optional[str] = None,
        max_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        backend = self._ensure()
        return backend.show_hands(
            show=show,
            save_path=save_path,
            max_hands=max_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def detect_pose(
        self,
        show: bool = True,
        save_path: Optional[str] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        backend = self._ensure()
        return backend.detect_pose(
            show=show,
            save_path=save_path,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def show_pose(
        self,
        show: bool = True,
        save_path: Optional[str] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        backend = self._ensure()
        return backend.show_pose(
            show=show,
            save_path=save_path,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def recognize_pose(
        self,
        show: bool = True,
        save_path: Optional[str] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        backend = self._ensure()
        return backend.recognize_pose(
            show=show,
            save_path=save_path,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )


class VoiceNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._tts_backend

    def say(self, text: str, block: bool = True, voice: Optional[str] = None):
        return self._owner.anim.speak(text=text, block=block, voice=voice)

    def speak(self, text: str, block: bool = True, voice: Optional[str] = None):
        return self.say(text=text, block=block, voice=voice)

    def voices(self):
        return self._owner.anim.show_voices()

    def show_voices(self):
        return self.voices()

    def set_volume(self, percent: int, control: Optional[str] = None):
        backend = self._ensure()
        fn = getattr(backend, "set_volume", None)
        if not callable(fn):
            raise AttributeError("tts_lib.set_volume is not available")
        return fn(percent, control=control)

    def get_volume(self, control: Optional[str] = None):
        backend = self._ensure()
        fn = getattr(backend, "get_volume", None)
        if not callable(fn):
            raise AttributeError("tts_lib.get_volume is not available")
        return fn(control=control)

    def select(self, voice: Optional[str] = None, number: Optional[int] = None):
        return self._owner.anim.select_voice(voice=voice, number=number)

    def select_voice(self, voice: Optional[str] = None, number: Optional[int] = None):
        return self.select(voice=voice, number=number)

    def select_voice_number(self, number: int):
        return self.select(number=number)

    def generate(self, key: str, text: str, voice: Optional[str] = None, length_scale: str = "0.98", sentence_silence: str = "0.08"):
        return self._owner.anim.generate_phrase(key=key, text=text, voice=voice, length_scale=length_scale, sentence_silence=sentence_silence)

    def generate_phrase(self, key: str, text: str, voice: Optional[str] = None, length_scale: str = "0.98", sentence_silence: str = "0.08"):
        return self.generate(key=key, text=text, voice=voice, length_scale=length_scale, sentence_silence=sentence_silence)

    def play(self, key: str, block: bool = True):
        return self._owner.anim.play_phrase(key=key, block=block)

    def play_phrase(self, key: str, block: bool = True):
        return self.play(key=key, block=block)


class BuzzerNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._buzzer_backend

    def horn(self, block: bool = True):
        return self._owner.horn(block=block)

    def beep(self, *args, **kwargs):
        backend = self._ensure()
        return backend.beep(*args, **kwargs)

    def play_notes(self, score: str, bpm: int = 120):
        backend = self._ensure()
        return backend.play_notes(score, bpm=bpm)

    def play_notes_music_mode(self, score: str, bpm: int = 120):
        backend = self._ensure()
        return backend.play_notes_music_mode(score, bpm=bpm)

    def play_melody(self, notes, bpm: int = 120):
        backend = self._ensure()
        return backend.play_melody(notes, bpm=bpm)


class SonarNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._sonar_backend

    def wait(self, timeout_s: float = 2.0):
        backend = self._ensure()
        return int(backend.wait_for_reading(timeout_s=timeout_s))

    def distance_cm(self, filtered: bool = True):
        backend = self._ensure()
        return int(backend.get_distance_cm(filtered=filtered) or 0)

    def distance_mm(self, filtered: bool = True):
        backend = self._ensure()
        return int(backend.get_distance_mm(filtered=filtered) or 0)

    def is_closer_than(self, threshold_cm: float, filtered: bool = True):
        backend = self._ensure()
        return backend.is_closer_than(threshold_cm=threshold_cm, filtered=filtered)


class InfraredNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._infrared_backend


class LineNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._line_backend

    def use_pid(self):
        self._owner._ensure_backends(line_mode="pid")
        return self._owner._line_backend

    def use_camera(self):
        self._owner._ensure_backends(line_mode="ros")
        return self._owner._line_backend


class TrackingNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._tracking_backend


class AvoidanceNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._avoidance_backend


class QRCodeNamespace(_BackendProxy):
    def _get_backend(self):
        return self._owner._qrcode_backend


class RobotV2:
    def __init__(
        self,
        base_speed: float = 300.0,
        rate_hz: float = 20.0,
        prefer_student_moves: bool = True,
        verbose: bool = True,
    ):
        self.base_speed = float(base_speed)
        self.rate_hz = float(rate_hz)
        self.prefer_student_moves = bool(prefer_student_moves)
        self.verbose = bool(verbose)
        self._errors: dict[str, str] = {}

        self._rm = None
        self._student_moves = None
        self._move_backend = None
        self._move_backends = []
        self._eyes_backend = None
        self._camera_backend = None
        self._tts_backend = None
        self._buzzer_backend = None
        self._sonar_backend = None
        self._vision_backend = None
        self._infrared_backend = None
        self._line_backend = None
        self._tracking_backend = None
        self._avoidance_backend = None
        self._qrcode_backend = None
        self._animation_backend = None

        self.move = MoveNamespace(self)
        self.eyes = EyesNamespace(self)
        self.camera = CameraNamespace(self)
        self.vision = VisionNamespace(self)
        self.voice = VoiceNamespace(self)
        self.buzzer = BuzzerNamespace(self)
        self.sonar = SonarNamespace(self)
        self.ultrasonic = self.sonar
        self.infrared = InfraredNamespace(self)
        self.line = LineNamespace(self)
        self.tracking = TrackingNamespace(self)
        self.avoidance = AvoidanceNamespace(self)
        self.qrcode = QRCodeNamespace(self)
        self.tts = self.voice
        self.sound = self.buzzer
        self.ultra = self.sonar

        self._ensure_backends()

    def _status(self, *parts):
        if self.verbose:
            print("[robot_v2]", *parts)

    def _import(self, module_name: str):
        try:
            return importlib.import_module(module_name)
        except Exception as e:
            self._errors[module_name] = str(e)
            return None

    def _import_student_animation_lib(self):
        mod = self._import("student_animation_lib")
        if mod is not None and callable(getattr(mod, "get_animation_lib", None)):
            return mod

        tried = []
        for base in [Path(__file__).resolve().parents[2], Path.cwd()]:
            candidate = base / "lessons" / "lib" / "student_animation_lib.py"
            tried.append(str(candidate))
            if not candidate.exists():
                continue
            try:
                spec = importlib.util.spec_from_file_location("_mata_student_animation_lib", str(candidate))
                if spec is None or spec.loader is None:
                    continue
                loaded = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(loaded)
                if callable(getattr(loaded, "get_animation_lib", None)):
                    return loaded
            except Exception as e:
                self._errors["student_animation_lib"] = str(e)

        source = getattr(mod, "__file__", "unknown file") if mod is not None else "not imported"
        self._errors["student_animation_lib"] = (
            "student_animation_lib missing get_animation_lib; "
            f"imported {source}; tried {tried}"
        )
        return mod

    def _move_aliases(self, move_name: str):
        aliases = {
            "forward": ("forward", "move_forward"),
            "backward": ("backward", "move_backward"),
            "left": ("left", "move_left"),
            "right": ("right", "move_right"),
            "turn_left": ("turn_left", "spin_left"),
            "turn_right": ("turn_right", "spin_right"),
            "diagonal_left": ("diagonal_left",),
            "diagonal_right": ("diagonal_right",),
            "drift_left": ("drift_left",),
            "drift_right": ("drift_right",),
            "stop": ("stop", "emergency_stop"),
        }
        return aliases.get(move_name, (move_name,))

    def _build_move_backends(self):
        self._rm = self._import("robot_moves")
        self._student_moves = self._import("student_robot_moves")

        if self._rm is not None:
            _call_if_callable(getattr(self._rm, "set_base_speed", None), self.base_speed)
            _call_if_callable(getattr(self._rm, "set_rate", None), self.rate_hz)

        if self._student_moves is not None:
            try:
                if hasattr(self._student_moves, "BASE_SPEED"):
                    self._student_moves.BASE_SPEED = self.base_speed
                if hasattr(self._student_moves, "RATE_HZ"):
                    self._student_moves.RATE_HZ = self.rate_hz
                _call_if_callable(getattr(self._student_moves, "setup", None))
            except Exception as e:
                self._errors["student_robot_moves"] = str(e)

        order = [self._student_moves, self._rm] if self.prefer_student_moves else [self._rm, self._student_moves]
        self._move_backends = [b for b in order if b is not None]
        self._move_backend = self._move_backends[0] if self._move_backends else None

    def _movement_backend_name(self) -> str:
        if self._move_backend is self._student_moves and self._student_moves is not None:
            return "student_robot_moves"
        if self._move_backend is self._rm and self._rm is not None:
            return "robot_moves"
        if self._move_backend is None:
            return "unavailable"
        return type(self._move_backend).__name__

    def _refresh_animation_backend(self):
        if self._animation_backend is not None:
            try:
                self._animation_backend = self._import_student_animation_lib().get_animation_lib(
                    robot=self._move_backend,
                    eyes=self._eyes_backend,
                    camera=self._camera_backend,
                    tts=self._tts_backend,
                    base_speed=self.base_speed,
                    verbose=self.verbose,
                )
            except Exception as e:
                self._errors["student_animation_lib"] = str(e)

    def _ensure_backends(self, line_mode: str = "pid"):
        if self._move_backend is None:
            self._build_move_backends()

        if self._eyes_backend is None:
            eyes_lib = self._import("eyes_lib")
            if eyes_lib is not None:
                try:
                    self._eyes_backend = eyes_lib.get_eyes()
                except Exception:
                    try:
                        self._eyes_backend = eyes_lib.get_eyes(force_reset=True)
                    except Exception as e:
                        self._errors["eyes_lib"] = str(e)

        if self._camera_backend is None:
            cam_lib = self._import("camera_lib")
            if cam_lib is not None:
                try:
                    self._camera_backend = cam_lib.get_camera()
                except Exception as e:
                    self._errors["camera_lib"] = str(e)

        if self._tts_backend is None:
            self._tts_backend = self._import("tts_lib")

        if self._buzzer_backend is None:
            buzzer_lib = self._import("buzzer_lib")
            if buzzer_lib is not None:
                try:
                    self._buzzer_backend = buzzer_lib.get_buzzer()
                except Exception as e:
                    self._errors["buzzer_lib"] = str(e)

        if self._sonar_backend is None:
            sonar_lib = self._import("sonar_lib")
            if sonar_lib is not None:
                try:
                    self._sonar_backend = sonar_lib.get_sonar()
                except Exception as e:
                    self._errors["sonar_lib"] = str(e)

        if self._vision_backend is None:
            vision_lib = self._import("vision_lib")
            if vision_lib is not None:
                try:
                    self._vision_backend = vision_lib.get_vision()
                except Exception as e:
                    self._errors["vision_lib"] = str(e)

        if self._infrared_backend is None:
            ir_lib = self._import("infrared_lib")
            if ir_lib is not None:
                try:
                    self._infrared_backend = ir_lib.get_infrared()
                except Exception as e:
                    self._errors["infrared_lib"] = str(e)

        if self._line_backend is None or line_mode == "ros":
            line_lib = self._import("line_follower_lib")
            if line_lib is not None:
                try:
                    if line_mode == "ros":
                        self._line_backend = line_lib.get_ros_line_follower()
                    elif self._line_backend is None:
                        self._line_backend = line_lib.LineFollower(infrared=self._infrared_backend) if self._infrared_backend is not None else None
                except Exception as e:
                    self._errors["line_follower_lib"] = str(e)

        if self._tracking_backend is None:
            tracking_lib = self._import("tracking_lib")
            if tracking_lib is not None:
                try:
                    self._tracking_backend = tracking_lib.get_tracking()
                except Exception as e:
                    self._errors["tracking_lib"] = str(e)

        if self._avoidance_backend is None:
            avoidance_lib = self._import("avoidance_lib")
            if avoidance_lib is not None:
                try:
                    self._avoidance_backend = avoidance_lib.get_avoidance()
                except Exception as e:
                    self._errors["avoidance_lib"] = str(e)

        if self._qrcode_backend is None:
            qrcode_lib = self._import("qrcode_lib")
            if qrcode_lib is not None:
                try:
                    self._qrcode_backend = qrcode_lib.get_qrcode()
                except Exception as e:
                    self._errors["qrcode_lib"] = str(e)

        if self._animation_backend is None:
            anim_lib = self._import_student_animation_lib()
            if anim_lib is not None:
                try:
                    self._animation_backend = anim_lib.get_animation_lib(
                        robot=self._move_backend,
                        eyes=self._eyes_backend,
                        camera=self._camera_backend,
                        tts=self._tts_backend,
                        base_speed=self.base_speed,
                        verbose=self.verbose,
                    )
                except Exception as e:
                    self._errors["student_animation_lib"] = str(e)

    @property
    def anim(self):
        self._ensure_backends()
        return self._animation_backend

    def use_base_moves(self):
        self.prefer_student_moves = False
        self._build_move_backends()
        self._refresh_animation_backend()
        self._status("movement backend ->", self._movement_backend_name())
        return self

    def use_robot_moves(self):
        return self.use_base_moves()

    def use_student_moves(self):
        self.prefer_student_moves = True
        self._build_move_backends()
        self._refresh_animation_backend()
        self._status("movement backend ->", self._movement_backend_name())
        return self

    def horn(self, block: bool = True):
        if self.anim is not None:
            return self.anim.horn_normal(block=block)
        backend = self._move_backend
        if backend is None:
            raise RuntimeError("Movement backend unavailable")
        fn = getattr(backend, "horn", None)
        if callable(fn):
            return fn(block=block)
        raise AttributeError("horn is not available")

    def stop(self):
        stopped = False
        if self.anim is not None:
            try:
                self.anim.stop()
                stopped = True
            except Exception as e:
                self._errors["student_animation_lib.stop"] = str(e)

        for backend in self._move_backends:
            if backend is None:
                continue
            for name in ("stop", "emergency_stop"):
                fn = getattr(backend, name, None)
                if callable(fn):
                    try:
                        fn()
                        stopped = True
                    except Exception as e:
                        self._errors[f"{type(backend).__name__}.{name}"] = str(e)

        controller = self._import("robot_controller_api")
        if controller is not None:
            fn = getattr(controller, "all_stop", None)
            if callable(fn):
                try:
                    fn()
                    stopped = True
                except Exception as e:
                    self._errors["robot_controller_api.all_stop"] = str(e)

        if not stopped:
            raise AttributeError("stop is not available")

        return None

    def status(self):
        self._ensure_backends()
        print("student_robot_v2:", __version__)
        print("base_speed:", self.base_speed)
        print("rate_hz:", self.rate_hz)
        print("movement backend:", self._movement_backend_name())
        print("eyes:", "ready" if self._eyes_backend is not None else f"unavailable -> {self._errors.get('eyes_lib')}")
        print("camera:", "ready" if self._camera_backend is not None else f"unavailable -> {self._errors.get('camera_lib')}")
        print("tts:", "ready" if self._tts_backend is not None else f"unavailable -> {self._errors.get('tts_lib')}")
        print("buzzer:", "ready" if self._buzzer_backend is not None else f"unavailable -> {self._errors.get('buzzer_lib')}")
        print("sonar:", "ready" if self._sonar_backend is not None else f"unavailable -> {self._errors.get('sonar_lib')}")
        print("vision:", "ready" if self._vision_backend is not None else f"unavailable -> {self._errors.get('vision_lib')}")
        print("infrared:", "ready" if self._infrared_backend is not None else f"unavailable -> {self._errors.get('infrared_lib')}")
        print("line:", "ready" if self._line_backend is not None else f"unavailable -> {self._errors.get('line_follower_lib')}")
        print("tracking:", "ready" if self._tracking_backend is not None else f"unavailable -> {self._errors.get('tracking_lib')}")
        print("avoidance:", "ready" if self._avoidance_backend is not None else f"unavailable -> {self._errors.get('avoidance_lib')}")
        print("qrcode:", "ready" if self._qrcode_backend is not None else f"unavailable -> {self._errors.get('qrcode_lib')}")
        print("animation:", "ready" if self._animation_backend is not None else f"unavailable -> {self._errors.get('student_animation_lib')}")
        if self._errors:
            print("load_errors:")
            for name in sorted(self._errors):
                print(f" - {name}: {self._errors[name]}")

    def versions(self):
        versions = {"student_robot_v2": __version__}
        modules = [
            ("student_robot_moves", self._student_moves),
            ("robot_moves", self._rm),
            ("eyes_lib", self._import("eyes_lib")),
            ("camera_lib", self._import("camera_lib")),
            ("tts_lib", self._tts_backend),
            ("buzzer_lib", self._import("buzzer_lib")),
            ("sonar_lib", self._import("sonar_lib")),
            ("vision_lib", self._import("vision_lib")),
            ("ultrasonic_lib", self._import("ultrasonic_lib")),
            ("infrared_lib", self._import("infrared_lib")),
            ("line_follower_lib", self._import("line_follower_lib")),
            ("tracking_lib", self._import("tracking_lib")),
            ("avoidance_lib", self._import("avoidance_lib")),
            ("qrcode_lib", self._import("qrcode_lib")),
            ("student_animation_lib", self._import("student_animation_lib")),
        ]
        for name, mod in modules:
            if mod is not None:
                versions[name] = getattr(mod, "__version__", "unknown")
        return versions

    def show_versions(self):
        for name in sorted(self.versions()):
            print(f"{name}: {self.versions()[name]}")



def bot(base_speed: float = 300.0, rate_hz: float = 20.0, prefer_student_moves: bool = False, verbose: bool = True) -> RobotV2:
    with _get_lock():
        inst = get_process_singleton(_SINGLETON_KEY)
        if inst is None:
            inst = set_process_singleton(
                _SINGLETON_KEY,
                RobotV2(
                    base_speed=base_speed,
                    rate_hz=rate_hz,
                    prefer_student_moves=prefer_student_moves,
                    verbose=verbose,
                ),
            )
            return inst

        inst.base_speed = float(base_speed)
        inst.rate_hz = float(rate_hz)
        inst.prefer_student_moves = bool(prefer_student_moves)
        inst.verbose = bool(verbose)
        inst._ensure_backends()
        return inst


def reset_bot() -> None:
    with _get_lock():
        inst = get_process_singleton(_SINGLETON_KEY)
        if inst is not None:
            try:
                inst.stop()
            except Exception:
                pass
        clear_process_singleton(_SINGLETON_KEY)
