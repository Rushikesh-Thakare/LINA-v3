"""
LINA v3 — Setup / Install
"""

from setuptools import setup, find_packages

setup(
    name="lina-voice-assistant",
    version="3.0.0",
    description="LINA — AI Voice Assistant for Linux",
    author="Rushikesh Thakare",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "PyQt5>=5.15",
        "faster-whisper>=1.0.0",
        "openwakeword>=0.6.0",
        "anthropic>=0.40.0",
        "groq>=0.11.0",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "scipy>=1.11.0",
        "webrtcvad>=2.0.10",
        "edge-tts>=7.0.0",
        "pyttsx3>=2.90",
        "python-dotenv>=1.0.0",
        "psutil>=5.9.0",
    ],
    entry_points={
        "console_scripts": [
            "lina=lina.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Operating System :: POSIX :: Linux",
        "Environment :: X11 Applications :: Qt",
        "License :: OSI Approved :: MIT License",
    ],
)
