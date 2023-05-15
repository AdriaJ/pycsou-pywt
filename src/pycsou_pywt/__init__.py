try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

from .operator import WaveletDec2, stackedWaveletDec

# from .operator import Flip, NullFunc

__all__ = (
    "WaveletDec2",
    "stackedWaveletDec",
)