"""An ensemble Separator: runs other separators and averages their voices
stems (weighted), sample by sample. Different architectures make different
mistakes, so the average keeps the voice and halves each one's bleed.

Measured on No Game No Life dub clips with instrumental music mixed in at
0 dB (SDR of the voice vs the same separator on the clean clip, 12 mixtures):
Demucs htdemucs_ft 8.63 mean / 3.42 worst, best single RoFormer 9.76 / 2.87,
three RoFormers 9.94 / 2.88, three RoFormers + Demucs 9.90 / 3.46 - the
best worst case at the same mean, hence the default.

Settings (config.json "separators": {"ensemble": {...}}):
    members   {separator name: weight}, default {"roformer": 3, "demucs": 1}
              (roformer is itself the average of its models, so 3:1 weighs
              every model equally)
"""

from amv.plugins import Separator, register

register("separator", Separator("ensemble", "average of separators (RoFormer x3 + Demucs)",
                                "amv.plugins.ensemble.separate:isolate", order=5))
