"""Register Research Report 1.0."""
from alembic import op
from app.methodology.seeds.academic_migration import upgrade_academic_methodology, downgrade_academic_methodology
from app.methodology.seeds.research_report import data_v1
revision="0018_research_report_1_0"; down_revision="0017_internship_report_1_0"; branch_labels=None; depends_on=None
def upgrade(): upgrade_academic_methodology(op.get_bind(),data_v1)
def downgrade(): downgrade_academic_methodology(op.get_bind(),data_v1)
