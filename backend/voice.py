import os
import threading
from typing import Any, Dict, Optional


class VoiceTranscriptionError(RuntimeError):
    """Raised when local speech-to-text is unavailable or fails."""


_model = None
_model_lock = threading.Lock()
_model_signature: Optional[tuple[str, str, str, Optional[str]]] = None


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _voice_config() -> Dict[str, Any]:
    return {
        "enabled": _env_bool("VOICE_STT_ENABLED", True),
        "model": os.getenv("VOICE_STT_MODEL", "small").strip() or "small",
        "device": os.getenv("VOICE_STT_DEVICE", "cpu").strip() or "cpu",
        "compute_type": os.getenv("VOICE_STT_COMPUTE_TYPE", "int8").strip() or "int8",
        "language": os.getenv("VOICE_STT_LANGUAGE", "ru").strip() or None,
        "download_root": os.getenv("VOICE_STT_DOWNLOAD_ROOT", "").strip() or None,
        "beam_size": int(os.getenv("VOICE_STT_BEAM_SIZE", "5")),
        "vad_filter": _env_bool("VOICE_STT_VAD_FILTER", True),
    }


def get_voice_status() -> Dict[str, Any]:
    config = _voice_config()
    try:
        import faster_whisper  # noqa: F401
        dependency_available = True
    except Exception:
        dependency_available = False

    return {
        "enabled": config["enabled"],
        "dependency": "faster-whisper",
        "dependency_available": dependency_available,
        "model": config["model"],
        "device": config["device"],
        "compute_type": config["compute_type"],
        "language": config["language"] or "auto",
        "loaded": _model is not None,
    }


def _get_model():
    global _model, _model_signature

    config = _voice_config()
    if not config["enabled"]:
        raise VoiceTranscriptionError("Local voice transcription is disabled by VOICE_STT_ENABLED.")

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise VoiceTranscriptionError(
            "faster-whisper is not installed. Install backend dependencies or rebuild the backend image."
        ) from exc

    signature = (
        config["model"],
        config["device"],
        config["compute_type"],
        config["download_root"],
    )

    with _model_lock:
        if _model is not None and _model_signature == signature:
            return _model

        kwargs: Dict[str, Any] = {
            "device": config["device"],
            "compute_type": config["compute_type"],
        }
        if config["download_root"]:
            kwargs["download_root"] = config["download_root"]

        _model = WhisperModel(config["model"], **kwargs)
        _model_signature = signature
        return _model


def transcribe_audio_file(audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
    config = _voice_config()
    model = _get_model()
    segments, info = model.transcribe(
        audio_path,
        language=language or config["language"],
        beam_size=config["beam_size"],
        vad_filter=config["vad_filter"],
    )

    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    return {
        "text": text,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "model": config["model"],
        "device": config["device"],
        "compute_type": config["compute_type"],
    }
