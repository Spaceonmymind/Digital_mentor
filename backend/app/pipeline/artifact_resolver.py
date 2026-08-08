from app.core.errors import AppError


SUPPORTED_ARTIFACT_TYPES = {
    "UNIVERSAL_DOCUMENT",
    "STARTUP_VKR",
}


class ArtifactResolver:
    async def resolve(
        self,
        artifact_type: str | None,
        filename: str,
        metadata: dict,
    ) -> str:
        if artifact_type:
            normalized = artifact_type.strip().upper()
            if normalized not in SUPPORTED_ARTIFACT_TYPES:
                raise AppError(
                    "UNSUPPORTED_ARTIFACT_TYPE",
                    "Тип артефакта не поддерживается",
                    status_code=400,
                    details={"artifact_type": normalized},
                )
            return normalized

        source = f"{filename} {' '.join(str(value) for value in metadata.values())}".lower()
        if any(marker in source for marker in ("startup", "вкр", "стартап")):
            return "STARTUP_VKR"
        return "UNIVERSAL_DOCUMENT"
