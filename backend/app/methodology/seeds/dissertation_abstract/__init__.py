from app.methodology.seeds.academic_common import ensure_academic_seed
from app.methodology.seeds.dissertation_abstract import data_v1
async def ensure_dissertation_abstract_seed(session): return await ensure_academic_seed(session, data_v1)
