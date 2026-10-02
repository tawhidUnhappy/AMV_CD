"""ffmpeg -af chains for the built-in song effects."""

from __future__ import annotations


def rate_chain(sample_rate: int, settings: dict) -> str:
    # asetrate changes speed AND pitch together - the slowed/nightcore sound,
    # unlike atempo which keeps the pitch.
    chain = f"asetrate={round(sample_rate * float(settings['rate']))},aresample={sample_rate}"
    if settings.get("reverb"):
        chain += ",aecho=0.8:0.85:50|95|160|240:0.35|0.27|0.2|0.13,volume=0.9"
    return chain
