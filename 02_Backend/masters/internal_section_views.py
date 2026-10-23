from .models import InternalSection
from .internal_section_forms import InternalSectionForm
from .views import create_master_views


internal_section_list, internal_section_create, internal_section_update, internal_section_toggle, internal_section_bulk_delete = create_master_views(
    InternalSection,
    InternalSectionForm,
    'Internal Section',
    'internal_section',
)
