"""Clean-up chain for synthesized speech: spectral denoise, de-esser, tone shelves, peak limit.

Invariant: float32 mono in, float32 mono out at the same sample rate; never clips above the peak limit.
Usage (samples): python scripts/voice_clean.py out/voice_bench/silero_eugene.wav
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import signal

PEAK_LIMIT_DBFS = -1.0


def _shelf(x: np.ndarray, sr: int, f0: float, gain_db: float, kind: str) -> np.ndarray:
    """RBJ low/high shelf biquad (S=1)."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    cosw, sinw = np.cos(w0), np.sin(w0)
    alpha = sinw / 2 * np.sqrt(2)
    if kind == "low":
        b = [A * ((A + 1) - (A - 1) * cosw + 2 * np.sqrt(A) * alpha),
             2 * A * ((A - 1) - (A + 1) * cosw),
             A * ((A + 1) - (A - 1) * cosw - 2 * np.sqrt(A) * alpha)]
        a = [(A + 1) + (A - 1) * cosw + 2 * np.sqrt(A) * alpha,
             -2 * ((A - 1) + (A + 1) * cosw),
             (A + 1) + (A - 1) * cosw - 2 * np.sqrt(A) * alpha]
    else:
        b = [A * ((A + 1) + (A - 1) * cosw + 2 * np.sqrt(A) * alpha),
             -2 * A * ((A - 1) + (A + 1) * cosw),
             A * ((A + 1) + (A - 1) * cosw - 2 * np.sqrt(A) * alpha)]
        a = [(A + 1) - (A - 1) * cosw + 2 * np.sqrt(A) * alpha,
             2 * ((A - 1) - (A + 1) * cosw),
             (A + 1) - (A - 1) * cosw - 2 * np.sqrt(A) * alpha]
    sos = np.array([[b[0] / a[0], b[1] / a[0], b[2] / a[0], 1.0, a[1] / a[0], a[2] / a[0]]])
    return signal.sosfilt(sos, x).astype(np.float32)


def denoise(x: np.ndarray, sr: int, over: float = 2.0, floor: float = 0.05) -> np.ndarray:
    """Spectral subtraction; noise profile = mean spectrum of the quietest 10% of frames."""
    nperseg, hop = 1024, 256
    _, _, Z = signal.stft(x, fs=sr, nperseg=nperseg, noverlap=nperseg - hop)
    mag, phase = np.abs(Z), np.angle(Z)
    frame_energy = np.sum(mag ** 2, axis=0)
    quiet = frame_energy <= np.percentile(frame_energy, 10)
    noise = np.mean(mag[:, quiet], axis=1, keepdims=True)
    clean = np.maximum(mag - over * noise, floor * mag)
    _, y = signal.istft(clean * np.exp(1j * phase), fs=sr, nperseg=nperseg, noverlap=nperseg - hop)
    y = y[: len(x)]
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    return y.astype(np.float32)


def deess(x: np.ndarray, sr: int, max_cut_db: float = 10.0, over_db: float = 0.0, ratio: float = 4.0) -> np.ndarray:
    """De-esser in the STFT domain: only bins 4-9 kHz are attenuated.

    Per frame, band level above (75th percentile + over_db) is reduced by (1 - 1/ratio), capped at max_cut_db.
    Frame gains are smoothed over 3 frames to avoid zipper noise. Bins outside the band are untouched.
    """
    nperseg, hop = 1024, 256
    f, _, Z = signal.stft(x, fs=sr, nperseg=nperseg, noverlap=nperseg - hop)
    band_mask = (f >= 4000) & (f <= 9000)
    band_level = np.sqrt(np.mean(np.abs(Z[band_mask, :]) ** 2, axis=0) + 1e-12)
    level_db = 20 * np.log10(band_level)
    thr = np.percentile(level_db, 75) + over_db
    reduction = np.clip((level_db - thr) * (1.0 - 1.0 / ratio), 0.0, max_cut_db)
    gain_db = np.convolve(-reduction, [0.25, 0.5, 0.25], mode="same")
    gain = 10 ** (gain_db / 20)
    Z2 = Z.copy()
    Z2[band_mask, :] *= gain[np.newaxis, :]
    _, y = signal.istft(Z2, fs=sr, nperseg=nperseg, noverlap=nperseg - hop)
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    return y[: len(x)].astype(np.float32)


def tone(x: np.ndarray, sr: int) -> np.ndarray:
    """Firmer lows (+1.5 dB below 180 Hz), softer highs (-2.5 dB above 7 kHz)."""
    y = _shelf(x, sr, 180.0, 1.5, "low")
    y = _shelf(y, sr, 7000.0, -2.5, "high")
    return y


def _peaking(x: np.ndarray, sr: int, f0: float, gain_db: float, q: float) -> np.ndarray:
    """RBJ peaking EQ biquad."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    cosw = np.cos(w0)
    b = [1 + alpha * A, -2 * cosw, 1 - alpha * A]
    a = [1 + alpha / A, -2 * cosw, 1 - alpha / A]
    sos = np.array([[b[0] / a[0], b[1] / a[0], b[2] / a[0], 1.0, a[1] / a[0], a[2] / a[0]]])
    return signal.sosfilt(sos, x).astype(np.float32)


def compress(x: np.ndarray, sr: int, thr_db: float, ratio: float, attack_ms: float = 5.0,
             release_ms: float = 80.0, makeup_db: float = 0.0) -> np.ndarray:
    """Feed-forward peak compressor with one-pole attack/release envelope."""
    a_att = np.exp(-1.0 / (sr * attack_ms / 1000.0))
    a_rel = np.exp(-1.0 / (sr * release_ms / 1000.0))
    level = np.abs(x).astype(np.float64)
    env = np.empty_like(level)
    e = 0.0
    for i, v in enumerate(level):
        coef = a_att if v > e else a_rel
        e = coef * e + (1.0 - coef) * v
        env[i] = e
    env_db = 20 * np.log10(env + 1e-9)
    over = np.maximum(env_db - thr_db, 0.0)
    gain_db = -over * (1.0 - 1.0 / ratio) + makeup_db
    return (x * 10 ** (gain_db / 20)).astype(np.float32)


def firm(x: np.ndarray, sr: int, target_rms_dbfs: float = -18.0) -> np.ndarray:
    """Firmer voice: low-mid body (+4.5 dB shelf at 150 Hz, the main spectral difference to the firmer speaker),
    gentle compression, RMS raised to target via makeup gain, then a brickwall limiter at -1 dBFS.
    The limiter replaces scaling the whole file, so the RMS target is actually reached."""
    y = _shelf(x, sr, 150.0, 4.5, "low")
    y = compress(y, sr, thr_db=-26.0, ratio=2.5)
    rms_db = 20 * np.log10(np.sqrt(np.mean(y.astype(np.float64) ** 2)) + 1e-12)
    y = y * 10 ** ((target_rms_dbfs - rms_db) / 20)
    y = compress(y, sr, thr_db=PEAK_LIMIT_DBFS, ratio=20.0, attack_ms=1.0, release_ms=50.0)
    return limit_peak(y)


def limit_peak(x: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(x))) + 1e-12
    target = 10 ** (PEAK_LIMIT_DBFS / 20)
    if peak > target:
        x = x * (target / peak)
    return x.astype(np.float32)


def clean(x: np.ndarray, sr: int) -> np.ndarray:
    y = denoise(x, sr)
    y = deess(y, sr)
    y = tone(y, sr)
    return limit_peak(y)


def band_db(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    f, p = signal.welch(x, fs=sr, nperseg=2048)
    m = (f >= lo) & (f < hi)
    return 10 * np.log10(np.sum(p[m]) + 1e-20)


def pause_floor_db(x: np.ndarray, sr: int) -> float:
    win = int(0.02 * sr)
    n = len(x) // win
    rms = np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(np.percentile(rms, 10))


def report(name: str, x: np.ndarray, sr: int) -> str:
    sib = band_db(x, sr, 4000, 9000)
    speech = band_db(x, sr, 300, 3000)
    return (f"{name:28} sibilance(4-9k)/speech(0.3-3k) = {sib - speech:6.1f} dB   "
            f"pause floor = {pause_floor_db(x, sr):6.1f} dBFS")


if __name__ == "__main__":
    import scipy.io.wavfile as wavfile

    out_dir = Path("out/voice_bench/clean")
    out_dir.mkdir(parents=True, exist_ok=True)
    for arg in sys.argv[1:]:
        p = Path(arg)
        sr, d = wavfile.read(p)
        x = d.astype(np.float32) / 32768.0
        y = clean(x, sr)
        print(report(p.name + " raw", x, sr))
        print(report(p.name + " clean", y, sr))
        wavfile.write(str(out_dir / f"{p.stem}_clean.wav"), sr, (np.clip(y, -1, 1) * 32767).astype(np.int16))
