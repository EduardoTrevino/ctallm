"""
live_cta_agent.py
A minimal live CTA data-collector & LLM prompter for digital tasks.
Author: (c) 2025 – MIT-style license
"""

import os, time, json, queue, threading
from datetime import datetime, timedelta

from openai import OpenAI
import psutil
from pynput import keyboard, mouse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import sounddevice as sd
import soundfile as sf
import tkinter as tk
from tkinter import messagebox, simpledialog

from dotenv import load_dotenv, find_dotenv

# Load .env.local if present, else fall back to .env
dotenv_path = find_dotenv(".env.local") or find_dotenv()
load_dotenv(dotenv_path, override=False)

client = OpenAI()  # automatically picks up OPENAI_API_KEY

# ──────────────────────────  SENSORS  ────────────────────────── #
class TelemetryBuffer:
    """Thread-safe circular buffer of (timestamp, event_str)."""
    def __init__(self, maxlen=500):
        self.maxlen = maxlen
        self.buf   = queue.deque(maxlen=maxlen)
        self.lock  = threading.Lock()

    def add(self, ev):
        with self.lock:
            self.buf.append((time.time(), ev))

    def snapshot(self, last_n_secs=60):
        cutoff = time.time() - last_n_secs
        with self.lock:
            return [f"{datetime.fromtimestamp(ts).isoformat()}  {txt}"
                    for ts, txt in self.buf if ts >= cutoff]

# Active window title every second (cross-platform)
def poll_active_window(telemetry, stop_event):
    import platform, subprocess, re
    while not stop_event.is_set():
        try:
            if platform.system() == "Windows":
                import ctypes, win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
            elif platform.system() == "Darwin":
                title = subprocess.check_output(
                    ["osascript","-e",'tell app "System Events" to get name of (process 1 where frontmost is true)']
                ).decode().strip()
            else:   # Linux (X)
                title = subprocess.check_output(
                    ["xdotool","getactivewindow","getwindowname"]
                ).decode().strip()
            telemetry.add(f"[win] {title}")
        except Exception as e:
            telemetry.add(f"[win] ERROR {e}")
        time.sleep(1)

# Keyboard / mouse hooks
def hook_input(telemetry, stop_event):
    def on_press(key):
        telemetry.add(f"[key] {key}")
    def on_click(x,y,button,pressed):
        if pressed: telemetry.add(f"[mouse] {button} at {x},{y}")
    with keyboard.Listener(on_press=on_press) as kl, \
         mouse.Listener(on_click=on_click) as ml:
        while not stop_event.is_set():
            time.sleep(0.1)

# File system watcher (current working directory recursive)
class FSHandler(FileSystemEventHandler):
    def __init__(self, telemetry): self.telemetry = telemetry
    def on_created(self, event): self.telemetry.add(f"[file+] {event.src_path}")
    def on_modified(self, event): self.telemetry.add(f"[file~] {event.src_path}")

def watch_fs(path, telemetry, stop_event):
    handler = FSHandler(telemetry)
    obs = Observer(); obs.schedule(handler, path, recursive=True); obs.start()
    while not stop_event.is_set(): time.sleep(0.5)
    obs.stop(); obs.join()

# ───────────────────────  RULE ENGINE  ───────────────────────── #
class TriggerEngine:
    """Very simple heuristics; replace with ML / rules as desired."""
    def __init__(self):
        self.last_prompt = 0
        self.file_events = []

    def evaluate(self, telemetry):
        now = time.time()
        # 1) idle pause ≥ 5 s (no key or mouse event)
        recent = telemetry.snapshot(6)
        any_input = any(ev.startswith("[key]") or ev.startswith("[mouse]")
                        for ev in recent)
        if not any_input and now - self.last_prompt > 15:
            return "I noticed a short pause—what were you thinking through just now?"

        # 2) burst of ≥3 file opens in 30 s
        self.file_events = [ts for ts in self.file_events if now - ts < 30]
        self.file_events += [now] if any(ev.startswith("[file+]") for ev in recent) else []
        if len(self.file_events) >= 3 and now - self.last_prompt > 30:
            return "You opened several new files—how did you choose which ones mattered?"

        return None

# ────────────────────  LLM & AUDIO HELPERS  ──────────────────── #
def llm_generate_question(prompt_hint, context_lines):
    system = (
        "You are an expert CTA interviewer. Ask ONE concise question "
        "to reveal the user's hidden cues/decision-making, given context."
    )
    user_msg = "\n".join(
        ["Context (last 60 s, most recent last):", *context_lines[-40:], "", f"Suggested focus: {prompt_hint}"]
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
    )
    return completion.choices[0].message.content.strip()

def record_audio(fn, seconds=10, fs=16000):
    msgbox = messagebox.showinfo
    msgbox("Recording", "Speak now…")
    audio = sd.rec(int(seconds*fs), samplerate=fs, channels=1)
    sd.wait()
    sf.write(fn, audio, fs)
    msgbox("Done", "Recording finished.")

def transcribe_audio(fn):
    with open(fn, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            # response_format="text",  # optional, default is JSON with .text
        )
    return transcription.text

# ──────────────────────────  GUI  ────────────────────────────── #
class CTAGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Live-CTA Recorder"); self.geometry("260x120")
        self.start_btn = tk.Button(self, text="TASK  START", width=20,
                                   command=self.start_task, bg="green", fg="white")
        self.stop_btn  = tk.Button(self, text="TASK  STOP",  width=20,
                                   command=self.stop_task, state="disabled",
                                   bg="red", fg="white")
        self.start_btn.pack(pady=10); self.stop_btn.pack()
        self.telemetry = TelemetryBuffer()
        self.stop_event = threading.Event()
        self.trigger   = TriggerEngine()
        self.running_threads = []

        self.monitor_loop()   # start idle loop

    def start_task(self):
        self.stop_event.clear(); self.start_time = time.time()
        for target in (poll_active_window, hook_input,
                       lambda t,s: watch_fs(os.getcwd(), t, s)):
            th = threading.Thread(target=target, args=(self.telemetry, self.stop_event),
                                  daemon=True); th.start(); self.running_threads.append(th)
        self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal")

    def stop_task(self):
        self.stop_event.set()
        for th in self.running_threads: th.join()
        self.running_threads.clear()
        self.dump_log()
        self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled")
        messagebox.showinfo("Saved","Session log saved.")

    def monitor_loop(self):
        if not self.stop_event.is_set():
            hint = self.trigger.evaluate(self.telemetry)
            if hint:
                ctx = self.telemetry.snapshot(60)
                question = llm_generate_question(hint, ctx)
                self.ask_cta_question(question, ctx)
                self.trigger.last_prompt = time.time()
        self.after(1000, self.monitor_loop)

    def ask_cta_question(self, question, ctx):
        answer = None
        if messagebox.askyesno("CTA", f"{question}\n\nRecord answer?"):
            wav_fn = f"ans_{int(time.time())}.wav"
            record_audio(wav_fn, seconds=12)
            answer = transcribe_audio(wav_fn)
            os.remove(wav_fn)
        # Store Q&A + context
        with open("cta_log.jsonl","a",encoding="utf8") as f:
            json.dump({"ts":datetime.now().isoformat(),
                       "question":question,
                       "answer":answer,
                       "context":ctx[-20:]}, f); f.write("\n")

    def dump_log(self):
        fn = f"session_{int(self.start_time)}.log"
        with open(fn,"w",encoding="utf8") as f:
            for line in self.telemetry.snapshot(10**9):
                f.write(line+"\n")

if __name__ == "__main__":
    CTAGUI().mainloop()
