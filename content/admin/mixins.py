from django import forms


class CantModifyRelatedMixin(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if hasattr(self, 'dont_modify_related'):
            for field_name in self.dont_modify_related:
                field = self.fields.get(field_name, None)
                if field:
                    w = field.widget
                    w.can_add_related = \
                        w.can_change_related = \
                        w.can_delete_related = False
