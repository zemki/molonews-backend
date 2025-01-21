from pydash import clone_deep

from django.contrib.auth.admin import UserAdmin

from .mixins import CantModifyRelatedMixin


class CustomUserForm(CantModifyRelatedMixin, UserAdmin.form):

    dont_modify_related = ('groups', 'sources',)


fieldsets = clone_deep(UserAdmin.fieldsets)

fieldsets[1][1]['fields'] += ('phone','area')

fieldsets[2][1]['fields'] += ('sources', 'can_publish', 'can_modify_organization_info' )


class CustomUserAdmin(UserAdmin):
    fieldsets = fieldsets
    form = CustomUserForm
    change_form_template = 'loginas/change_form.html'

     # Make date_joined visible in the admin list view
    list_display = ('username', 'email', 'date_joined', 'is_active', 'is_staff')  # Add other fields as needed

    # Allow sorting by date_joined (default ascending order)
    ordering = ('-date_joined',)  # Change to 'date_joined' for ascending order

    # Optional: Allow filtering by date_joined
    list_filter = ('date_joined', 'is_staff', 'is_superuser', 'is_active')

