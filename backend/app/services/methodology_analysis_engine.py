from app.core.errors import AppError
from app.db.session import async_session_factory
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository
from app.schemas.results import AnalysisResultPayload


class MethodologyAnalysisEngine:
    """Selects an executor from versioned methodology configuration, not work type branches."""

    async def run(
        self,
        analysis_id: str,
        document_id: str,
        methodology_id: str,
        methodology_version: str,
        mode: str = "standard",
    ) -> AnalysisResultPayload:
        async with async_session_factory() as session:
            methodology = await MethodologyRegistry(MethodologyRepository(session)).resolve_historical(
                methodology_id,
                methodology_version,
            )
            profile = (methodology.configuration or {}).get("execution_profile")
        executor = self._executor(profile)
        return await executor.run(
            analysis_id,
            document_id,
            methodology_id,
            methodology_version,
            mode=mode,
        )

    @staticmethod
    def _executor(profile: str | None):
        if profile == "startup_vkr":
            from app.execution.startup_vkr import StartupVkrAnalysisEngine

            return StartupVkrAnalysisEngine()
        if profile == "candidate_dissertation":
            from app.execution.candidate_dissertation import CandidateDissertationAnalysisEngine

            return CandidateDissertationAnalysisEngine()
        if profile == "scientific_article":
            from app.execution.scientific_article import ScientificArticleAnalysisEngine

            return ScientificArticleAnalysisEngine()
        if profile == "graduation_thesis":
            from app.execution.graduation_thesis import GraduationThesisAnalysisEngine

            return GraduationThesisAnalysisEngine()
        if profile == "master_dissertation":
            from app.execution.master_dissertation import MasterDissertationAnalysisEngine

            return MasterDissertationAnalysisEngine()
        if profile == "course_paper":
            from app.execution.course_paper import CoursePaperAnalysisEngine
            return CoursePaperAnalysisEngine()
        if profile == "internship_report":
            from app.execution.internship_report import InternshipReportAnalysisEngine
            return InternshipReportAnalysisEngine()
        if profile == "research_report":
            from app.execution.research_report import ResearchReportAnalysisEngine
            return ResearchReportAnalysisEngine()
        if profile == "doctoral_dissertation":
            from app.execution.doctoral_dissertation import DoctoralDissertationAnalysisEngine
            return DoctoralDissertationAnalysisEngine()
        if profile == "dissertation_abstract":
            from app.execution.dissertation_abstract import DissertationAbstractAnalysisEngine
            return DissertationAbstractAnalysisEngine()
        raise AppError(
            "METHODOLOGY_EXECUTION_PROFILE_NOT_CONFIGURED",
            "Для выбранной методологии не настроен исполнитель анализа",
            status_code=409,
            details={"execution_profile": profile},
        )
