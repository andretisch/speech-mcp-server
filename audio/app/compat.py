from __future__ import annotations

import typing as _typing


def patch_torchaudio_compat() -> None:
    """
    Compatibility for libraries expecting older torchaudio APIs:
    AudioMetaData, info, list_audio_backends.
    """
    try:
        import torchaudio  # type: ignore
    except Exception:
        return

    if not hasattr(torchaudio, "AudioMetaData"):
        from typing import NamedTuple

        class AudioMetaData(NamedTuple):
            sample_rate: int
            num_frames: int
            num_channels: int
            bits_per_sample: int
            encoding: str

        torchaudio.AudioMetaData = AudioMetaData  # type: ignore[attr-defined]

    if not hasattr(torchaudio, "list_audio_backends"):
        def list_audio_backends():  # type: ignore[no-redef]
            try:
                import soundfile  # noqa: F401

                return ["soundfile"]
            except Exception:
                return []

        torchaudio.list_audio_backends = list_audio_backends  # type: ignore[attr-defined]

    if not hasattr(torchaudio, "info"):
        def info(path, backend=None):  # type: ignore[no-redef]
            import soundfile as sf

            with sf.SoundFile(path) as f:
                sr = int(f.samplerate)
                frames = int(len(f))
                ch = int(f.channels)
                subtype = str(getattr(f, "subtype", "") or "")
            bps = 16
            if "24" in subtype:
                bps = 24
            elif "32" in subtype:
                bps = 32
            enc = subtype or "PCM"
            return torchaudio.AudioMetaData(sr, frames, ch, bps, enc)  # type: ignore[attr-defined]

        torchaudio.info = info  # type: ignore[attr-defined]


def patch_huggingface_hub_compat() -> None:
    """
    Compatibility for huggingface_hub token naming:
    map use_auth_token -> token.
    """
    try:
        import huggingface_hub as hfh  # type: ignore
    except Exception:
        return

    fn = getattr(hfh, "hf_hub_download", None)
    if not callable(fn):
        return

    def wrapped_hf_hub_download(*args, **kwargs):  # type: ignore[no-redef]
        if "use_auth_token" in kwargs and "token" not in kwargs:
            kwargs["token"] = kwargs.pop("use_auth_token")
        else:
            kwargs.pop("use_auth_token", None)
        return fn(*args, **kwargs)

    hfh.hf_hub_download = wrapped_hf_hub_download  # type: ignore[attr-defined]


def torch_safe_globals_ctx():
    """
    Local safe-globals context for torch.load(weights_only=True) in PyTorch 2.6+.
    """
    from contextlib import nullcontext

    try:
        import torch.serialization as ts  # type: ignore
        import types as _types
        import collections as _collections
        from omegaconf.base import ContainerMetadata
        from omegaconf.listconfig import ListConfig
        from omegaconf.dictconfig import DictConfig
        from omegaconf import nodes as _oc_nodes
    except Exception:
        return nullcontext()

    allow = [
        _typing.Any,
        ContainerMetadata,
        ListConfig,
        DictConfig,
        list,
        dict,
        tuple,
        set,
        frozenset,
        str,
        int,
        float,
        bool,
        bytes,
        type(None),
        _types.SimpleNamespace,
        _collections.defaultdict,
        getattr(_oc_nodes, "AnyNode", object),
        getattr(_oc_nodes, "ValueNode", object),
        getattr(_oc_nodes, "StringNode", object),
        getattr(_oc_nodes, "IntegerNode", object),
        getattr(_oc_nodes, "FloatNode", object),
        getattr(_oc_nodes, "BooleanNode", object),
    ]

    safe_globals = getattr(ts, "safe_globals", None)
    if callable(safe_globals):
        try:
            return safe_globals(allow)
        except Exception:
            return nullcontext()

    try:
        ts.add_safe_globals(allow)
    except Exception:
        pass
    return nullcontext()

