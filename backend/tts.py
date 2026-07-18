import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class VoiceSynthesisError(RuntimeError):
    """Raised when a configured local TTS provider cannot synthesize speech."""


def _tts_config() -> Dict[str, Any]:
    provider = (os.getenv("VOICE_TTS_PROVIDER", "auto").strip() or "auto").lower()
    return {
        "enabled": os.getenv("VOICE_TTS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
        "provider": provider,
        "piper_binary": os.getenv("VOICE_TTS_PIPER_BINARY", "piper").strip() or "piper",
        "piper_model": os.getenv("VOICE_TTS_PIPER_MODEL", "").strip(),
        "rhvoice_binary": os.getenv("VOICE_TTS_RHVOICE_BINARY", "RHVoice-test").strip() or "RHVoice-test",
        "voice": os.getenv("VOICE_TTS_VOICE", "").strip(),
        "timeout_seconds": max(2, int(os.getenv("VOICE_TTS_TIMEOUT_SECONDS", "30"))),
        "max_chars": max(200, int(os.getenv("VOICE_TTS_MAX_CHARS", "4000"))),
    }


def _binary_available(binary: str) -> bool:
    return bool(shutil.which(binary))


def _provider_status(provider: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if provider == "piper":
        model = Path(config["piper_model"]).expanduser() if config["piper_model"] else None
        return {
            "provider": "piper",
            "binary": config["piper_binary"],
            "binary_available": _binary_available(config["piper_binary"]),
            "model": str(model) if model else "",
            "model_available": bool(model and model.is_file()),
            "voice": config["voice"] or "model-default",
        }
    if provider == "rhvoice":
        return {
            "provider": "rhvoice",
            "binary": config["rhvoice_binary"],
            "binary_available": _binary_available(config["rhvoice_binary"]),
            "model": "",
            "model_available": True,
            "voice": config["voice"] or "default",
        }
    return {
        "provider": provider,
        "binary": "",
        "binary_available": False,
        "model": "",
        "model_available": False,
        "voice": config["voice"] or "default",
    }


def get_tts_status() -> Dict[str, Any]:
    config = _tts_config()
    candidates = ["piper", "rhvoice"] if config["provider"] == "auto" else [config["provider"]]
    statuses = [_provider_status(provider, config) for provider in candidates]
    active = next(
        (
            item
            for item in statuses
            if item["binary_available"] and item["model_available"]
        ),
        None,
    )
    return {
        "enabled": config["enabled"],
        "configured_provider": config["provider"],
        "available": bool(config["enabled"] and active),
        "active_provider": active["provider"] if active else None,
        "voice": active["voice"] if active else config["voice"] or None,
        "providers": statuses,
        "browser_fallback": True,
        "downloads_models": False,
    }


def _resolve_provider(config: Dict[str, Any]) -> Optional[str]:
    status = get_tts_status()
    return status["active_provider"]


def synthesize_speech(text: str, output_path: str, voice: Optional[str] = None, rate: float = 1.0) -> Dict[str, Any]:
    config = _tts_config()
    clean_text = "".join(character for character in text if character in "\n\t" or ord(character) >= 32).strip()
    if not clean_text:
        raise VoiceSynthesisError("Speech text is empty.")
    if len(clean_text) > config["max_chars"]:
        raise VoiceSynthesisError(f"Speech text is longer than {config['max_chars']} characters.")
    if not config["enabled"]:
        raise VoiceSynthesisError("Local speech synthesis is disabled by VOICE_TTS_ENABLED.")

    provider = _resolve_provider(config)
    if provider is None:
        raise VoiceSynthesisError("No configured local TTS provider is ready.")

    output = str(Path(output_path).resolve())
    selected_voice = (voice or config["voice"]).strip()
    if provider == "piper":
        command = [
            config["piper_binary"],
            "-m",
            str(Path(config["piper_model"]).expanduser().resolve()),
            "-f",
            output,
        ]
        if rate != 1.0:
            command.extend(["--length-scale", f"{1 / rate:.3f}"])
    else:
        command = [config["rhvoice_binary"], "-o", output]
        if selected_voice:
            command.extend(["-p", selected_voice])
        if rate != 1.0:
            command.extend(["-r", f"{rate:.3f}"])

    try:
        completed = subprocess.run(
            command,
            input=clean_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=config["timeout_seconds"],
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VoiceSynthesisError(f"{provider} synthesis failed: {exc}") from exc

    if completed.returncode != 0 or not Path(output).is_file() or Path(output).stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or "no audio produced").strip()[:500]
        raise VoiceSynthesisError(f"{provider} synthesis failed: {detail}")

    return {
        "provider": provider,
        "voice": selected_voice or "default",
        "size_bytes": Path(output).stat().st_size,
    }
