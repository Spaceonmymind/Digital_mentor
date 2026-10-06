from app.methodology.seeds.academic_common import ensure_academic_seed
from app.methodology.seeds.doctoral_dissertation import data_v1
async def ensure_doctoral_dissertation_seed(session): return await ensure_academic_seed(session, data_v1)
