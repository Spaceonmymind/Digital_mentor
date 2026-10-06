from app.methodology.seeds.academic_common import ensure_academic_seed
from app.methodology.seeds.internship_report import data_v1
async def ensure_internship_report_seed(session): return await ensure_academic_seed(session, data_v1)
