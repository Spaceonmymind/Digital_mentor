from app.core.errors import AppError


SUPPORTED_ARTIFACT_TYPES = {
    "UNIVERSAL_DOCUMENT",
    "STARTUP_VKR",
    "CANDIDATE_DISSERTATION",
    "SCIENTIFIC_ARTICLE",
    "BACHELOR_SPECIALIST_THESIS",
    "MASTER_THESIS",
    "COURSE_WORK",
    "PRACTICE_REPORT",
    "RESEARCH_REPORT",
    "DOCTORAL_DISSERTATION",
    "DISSERTATION_ABSTRACT",
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

        # Methodology selection must be explicit; filenames and document text
        # are not a reliable or user-visible work type selection mechanism.
        return "UNIVERSAL_DOCUMENT"
