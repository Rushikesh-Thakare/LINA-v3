"""
LINA Voice package.
Contains STT, TTS, Wake Word, and VAD threads.
All I/O runs inside QThread subclasses — NEVER on the main Qt thread.
"""
